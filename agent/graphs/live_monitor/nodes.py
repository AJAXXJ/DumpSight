import logging
import re
import time
import uuid
from typing import Any

from langchain_core.output_parsers import StrOutputParser

from agent.config.alert_rules import load_alert_rules
from agent.config.llm_factory import get_llm
from agent.config.settings import get_settings
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.prompt_registry import get_registry
from agent.tools.tool_registry import get_tools

logger = logging.getLogger(__name__)
settings = get_settings()
_llm = get_llm()
_builder = PromptBuilder(registry=get_registry())
_tools = get_tools()
_alert_rules = load_alert_rules()
_cooldown_registry: dict[str, float] = {}

_last_cumulative_snapshot: dict[str, dict[str, float]] = {}


def _latest(metrics) -> dict:
    if isinstance(metrics, list):
        return metrics[-1] if metrics else {}
    return metrics or {}


def node_fetch_metrics(state, config):
    run_id = str(uuid.uuid4())
    cid, pid = state["client_id"], state["pid"]

    try:
        client_info = _tools["client_info"].invoke({"client_id": cid})
        dpdk_info   = _tools["dpdk_info"].invoke({"client_id": cid, "pid": pid})
        metrics_1s  = _tools["log_1s"].invoke({"client_id": cid, "pid": pid, "seconds": 10})
        metrics_5s  = _tools["log_5s"].invoke({"client_id": cid, "pid": pid, "seconds": 10})
    except Exception as exc:
        logger.exception("fetch_metrics failed | run_id=%s", run_id)
        return {"error": f"指标拉取失败: {exc}", "run_id": run_id}

    if not metrics_1s or not metrics_5s:
        logger.warning("fetch_metrics empty | run_id=%s", run_id)
        return {"error": f"客户端 {cid} DPDK {pid} 实例暂无日志数据", "run_id": run_id}

    last_snapshot = _last_cumulative_snapshot.get(cid, {})
    baseline = _extract_baseline(dpdk_info, metrics_1s, last_snapshot)
    _last_cumulative_snapshot[cid] = _take_cumulative_snapshot(metrics_1s)

    return {
        "run_id": run_id,
        "client_info": client_info,
        "dpdk_info": dpdk_info,
        "metrics_1s": metrics_1s,
        "metrics_5s": metrics_5s,
        "baseline": baseline,
        "alert_rules": _alert_rules,
        "error": "",
        "anomaly_flags": [],
        "should_alert": False,
        "escalate_to_fault": False,
    }


def _take_cumulative_snapshot(metrics_1s):
    """
    取列表最后一条快照，提取累计型指标当前值供下次计算增量。
    """
    ethdev = _latest(metrics_1s).get("ethdev_stats", {})
    return {
        "rx_errors":        sum(nic.get("rx_errors", 0)        for nic in ethdev.values()),
        "rx_nombuf":        sum(nic.get("rx_nombuf", 0)        for nic in ethdev.values()),
        "rx_missed_errors": sum(nic.get("rx_missed_errors", 0) for nic in ethdev.values()),
    }


def _extract_baseline(dpdk_info, metrics_1s, last_snapshot):
    ethdev = _latest(metrics_1s).get("ethdev_stats", {}) or {}

    def _delta(key):
        current = sum(
            nic.get(key, 0)
            for nic in ethdev.values()
            if isinstance(nic, dict)
        )
        return current - last_snapshot.get(key, current)

    return {
        "hugepage_free_mb":   dpdk_info.get("baseline_hugepage_free_mb", 2048),
        "port_drop_rate_pct": dpdk_info.get("baseline_drop_rate_pct", 0.0),
        "lcore_busy_pct":     dpdk_info.get("baseline_lcore_busy_pct", 60.0),
        "rx_queue_fill_pct":  dpdk_info.get("baseline_rx_fill_pct", 50.0),
        "rx_errors":          _delta("rx_errors"),
        "rx_nombuf":          _delta("rx_nombuf"),
        "rx_missed_errors":   _delta("rx_missed_errors"),
    }


def _resolve_metric(source, metric):
    """
    按 metric 路径解析指标值。
    source 为列表时，遍历所有快照取最大值（捕捉窗口内任意峰值）。
    """
    if isinstance(source, list):
        values = [_resolve_metric(s, metric) for s in source if isinstance(s, dict)]
        values = [v for v in values if v is not None]
        return float(max(values)) if values else None

    if metric.startswith("ethdev_stats."):
        field = metric.split(".", 1)[1]
        values = [
            nic.get(field)
            for nic in source.get("ethdev_stats", {}).values()
            if nic.get(field) is not None
        ]
        return float(max(values)) if values else None

    if metric.startswith("lcore_usage."):
        field = metric.split(".", 1)[1]
        lcores = source.get("lcore_usage", {}).get("lcores", [])
        values = [lc.get(field) for lc in lcores if lc.get(field) is not None]
        return float(max(values)) if values else None

    return _get_nested(source, metric)


def node_anomaly_detection(state, config):
    rule_flags = _run_rule_engine(
        state["metrics_1s"],
        state["metrics_5s"],
        state["baseline"],
        state["alert_rules"],
    )
    semantic_flags, escalate, prompt_meta = _run_semantic_detection(state, config)
    all_flags = _deduplicate(rule_flags + semantic_flags)

    logger.info(
        "anomaly_detection done | run_id=%s rule=%d semantic=%d total=%d",
        state.get("run_id"), len(rule_flags), len(semantic_flags), len(all_flags),
    )
    return {
        "anomaly_flags": all_flags,
        "escalate_to_fault": escalate,
        "prompt_meta": prompt_meta,
        "error": "",
    }


def _run_rule_engine(metrics_1s, metrics_5s, baseline, rules):
    flags = []
    for rule in rules:
        if not rule.enabled:
            continue
        source = metrics_1s if rule.source == "1s" else metrics_5s
        value = _resolve_metric(source, rule.metric)   # ✅ 自动处理列表
        if value is None:
            continue
        if _evaluate_condition(
            value,
            rule.condition,
            rule.threshold,
            _get_nested(baseline, rule.metric.split(".")[-1]),
        ):
            flags.append(rule.id)
            logger.debug("rule triggered | id=%s value=%s", rule.id, value)
    return flags


def _run_semantic_detection(state, config):
    try:
        messages, meta = _builder.build_anomaly_detection(
            metrics_1s=state["metrics_1s"],
            metrics_5s=state["metrics_5s"],
            baseline=state["baseline"],
            alert_rules=state["alert_rules"],
        )
        raw = StrOutputParser().invoke(_llm.invoke(messages, config=config))
        flags, escalate = _parse_semantic_output(raw)
        return flags, escalate, meta.as_log_dict()
    except Exception as exc:
        logger.warning("semantic detection failed, rule-only mode | %s", exc)
        return [], False, {}


def _parse_semantic_output(raw):
    flags = []
    if m := re.search(r"ANOMALIES:\s*(.+)", raw, re.IGNORECASE):
        raw_flags = m.group(1).strip()
        if raw_flags.upper() != "NONE":
            flags = [f.strip() for f in raw_flags.split(",") if f.strip()]
    escalate = bool(re.search(r"ESCALATE:\s*yes", raw, re.IGNORECASE))
    return flags, escalate


def _evaluate_condition(value, condition, threshold, baseline):
    match condition:
        case "gt":      return value > threshold
        case "lt":      return value < threshold
        case "gte":     return value >= threshold
        case "lte":     return value <= threshold
        case "eq":      return value == threshold
        case "delta_pct" if baseline not in (None, 0):
            pct = (value - baseline) / abs(baseline) * 100
            return pct > threshold if threshold >= 0 else pct < threshold
    return False


def _get_nested(d, key):
    cur: Any = d
    for p in key.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return float(cur) if cur is not None else None


def _deduplicate(flags):
    seen: set[str] = set()
    return [f for f in flags if not (f in seen or seen.add(f))]


def node_risk_assessment(state, config):
    flags = state.get("anomaly_flags", [])
    if not flags:
        return {"should_alert": False}

    severity  = _compute_severity(flags, state["alert_rules"])
    escalate  = state.get("escalate_to_fault", False) or _has_escalation_flag(flags, state["alert_rules"])
    client_id = state["client_info"].get("client_id", "unknown")

    if _in_cooldown(client_id, severity):
        logger.info("alert suppressed by cooldown | client=%s severity=%s", client_id, severity)
        return {"should_alert": False, "escalate_to_fault": escalate}

    _update_cooldown(client_id, severity)

    latest = _latest(state["metrics_1s"])
    return {
        "should_alert": True,
        "escalate_to_fault": escalate,
        "metrics_1s": {**latest, "_severity": severity},
    }


def _in_cooldown(client_id, severity):
    return (time.time() - _cooldown_registry.get(f"{client_id}:{severity}", 0.0)) < settings.alert_cooldown_sec


def _update_cooldown(client_id, severity):
    _cooldown_registry[f"{client_id}:{severity}"] = time.time()


def _compute_severity(flags, rules):
    rule_map   = {r.id: r for r in rules}
    severities = {rule_map[f].severity for f in flags if f in rule_map}
    return next((lv for lv in ("critical", "warning", "info") if lv in severities), "info")


def _has_escalation_flag(flags, rules):
    rule_map = {r.id: r for r in rules}
    return any(rule_map.get(f) and rule_map[f].escalate_to_fault for f in flags)


def node_alert_generation(state, config):
    severity  = state["metrics_1s"].get("_severity", "warning")
    client_id = state["client_info"].get("client_id", "unknown")

    messages, meta = _builder.build_alert_generation(
        anomaly_summary=", ".join(state.get("anomaly_flags", [])),
        severity=severity,
        client_id=client_id,
        metrics_snapshot=state["metrics_1s"],
    )

    try:
        raw = StrOutputParser().invoke(_llm.invoke(messages, config=config))
        title, description = _parse_alert_text(raw)
    except Exception as exc:
        logger.warning("alert LLM failed, using fallback text | %s", exc)
        title       = f"[{severity.upper()}] DPDK 异常 — {client_id}"
        description = f"触发规则: {', '.join(state.get('anomaly_flags', []))}"

    return {
        "alert": {
            "alert_id":    str(uuid.uuid4()),
            "severity":    severity,
            "title":       title,
            "description": description,
            "client_id":   client_id,
            "triggered_at": time.time(),
        },
        "prompt_meta": meta.as_log_dict() if meta else {},
        "error": "",
    }


def _parse_alert_text(raw):
    title = description = ""
    if m := re.search(r"TITLE:\s*(.+)", raw, re.IGNORECASE):
        title = m.group(1).strip()
    if m := re.search(r"DESCRIPTION:\s*([\s\S]+)", raw, re.IGNORECASE):
        description = m.group(1).strip()
    return title or raw[:80], description or raw


def node_escalate_to_fault(state, config):
    logger.warning(
        "escalating to fault analysis | client=%s flags=%s run_id=%s",
        state["client_info"].get("client_id"),
        state.get("anomaly_flags"),
        state.get("run_id"),
    )
    try:
        crash_stack   = _tools["crash_core"].invoke({})
        core_analysis = _tools["crash_core_analysis"].invoke({})
    except Exception as exc:
        logger.warning("crash data fetch failed during escalation | %s", exc)
        crash_stack = core_analysis = ""

    return {
        "escalate_to_fault": True,
        "crash_stack":   crash_stack,
        "core_analysis": core_analysis,
        "mode": "fault_analysis",
    }


def node_handle_error(state, config):
    logger.error(
        "realtime_monitor error | run_id=%s | %s",
        state.get("run_id"),
        state.get("error", "未知错误"),
    )
    return {"should_alert": False, "escalate_to_fault": False}


def cleanup_clients(client_ids):
    for client_id in client_ids:
        _last_cumulative_snapshot.pop(client_id, None)

    cooldown_keys = [k for k in _cooldown_registry if k.split(":")[0] in client_ids]
    for k in cooldown_keys:
        _cooldown_registry.pop(k, None)

    logger.info("client cache cleaned | clients=%s", client_ids)
