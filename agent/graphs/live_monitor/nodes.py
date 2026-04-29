import logging
import re
import threading
import time
import uuid
from typing import Any

from langchain_core.output_parsers import StrOutputParser

from agent.config.alert_rules import load_alert_rules
from agent.config.llm_factory import get_llm
from agent.config.settings import get_settings
from agent.prompts.prompt_builder import PromptBuilder
from agent.prompts.prompt_registry import get_registry
from agent.tools.telemetry_feature_tool import (
    build_llm_features,
    build_reference_features,
    log_1s_statistic,
    log_5s_statistic,
)
from agent.tools.tool_registry import get_tools

logger = logging.getLogger(__name__)
settings = get_settings()
_llm = get_llm()
_builder = PromptBuilder(registry=get_registry())
_tools = get_tools()
_alert_rules = load_alert_rules()

# key: "client_id:rule:<rule_id>"     → 规则级冷却（细粒度）
# key: "client_id:severity:<level>"   → severity级冷却（粗粒度兜底）
_cooldown_registry: dict[str, float] = {}

# 所有冷却读写都通过此锁保护，防止多线程 TOCTOU
_cooldown_lock = threading.Lock()

# reference_feature 模块级缓存，key: "client_id:pid"
_reference_cache: dict[str, dict] = {}
_reference_cache_lock = threading.Lock()
_REFERENCE_CACHE_TTL = 300.0  # 5分钟更新一次基线


def _latest(metrics) -> dict:
    """取指标列表的最后一条快照，兼容 list 和 dict 输入。"""
    if isinstance(metrics, list):
        return metrics[-1] if metrics else {}
    return metrics or {}


def _reset_state() -> dict:
    """
    返回每轮执行开始时所有输出字段的初始值。
    在 node_fetch_metrics 中调用，防止 LangGraph State 跨轮残留。

    注意：allow_semantic 不在此处重置，由调用层（run_fast/slow_poll）
    通过入参 state 传入，fetch_metrics 负责透传到输出 State。
    """
    return {
        "rule_flags": [],
        "semantic_flags": [],
        "anomaly_flags": [],
        "should_alert": False,
        # 将升级意图拆为两个独立字段，语义更清晰：
        #   - escalate_from_semantic: LLM 语义检测判定需要升级
        #   - escalate_to_fault:      最终由 risk_assessment 综合决定是否升级
        # edge_after_risk 和 edge_after_alert 只读 escalate_to_fault，
        # 由 risk_assessment 统一写入，消除双写竞争。
        "escalate_from_semantic": False,
        "escalate_to_fault": False,
        "alert_input": {},
        "alert": {},
        "prompt_meta": {},
        "crash_stack": "",
        "core_analysis": "",
        "mode": "",
        "error": "",
    }


def node_fetch_metrics(state, config):
    """
    数据拉取节点：拉取原始日志，提取 log_feature 和 reference_feature。

    流程：
        1. 重置所有输出字段，防止上轮 State 残留影响本轮路由
        2. 拉取最近 10s 的 1s/5s 日志，生成 log_feature
        3. 检查 reference_feature 缓存，过期才重新拉取（TTL=5min）
        4. 出错时返回 error 字段，由 edge_after_fetch 路由至 handle_error
    """
    run_id = str(uuid.uuid4())
    cid, pid = state["client_id"], state["pid"]

    # P0：每轮强制重置所有输出字段
    base = _reset_state()

    try:
        client_info = _tools["client_info"].invoke({"client_id": cid})
        dpdk_info = _tools["dpdk_info"].invoke({"client_id": cid, "pid": pid})
        metrics_1s = _tools["log_1s"].invoke(
            {"client_id": cid, "pid": pid, "seconds": 10}
        )
        metrics_5s = _tools["log_5s"].invoke(
            {"client_id": cid, "pid": pid, "seconds": 10}
        )

        if not metrics_1s or not metrics_5s:
            logger.warning("fetch_metrics empty | run_id=%s", run_id)
            return {
                **base,
                "error": f"客户端 {cid} DPDK {pid} 实例暂无日志数据",
                "run_id": run_id,
                # FIX [问题二]：allow_semantic 在 fetch_metrics 输出中显式保留，
                # 确保后续节点和边函数能稳定读取，不依赖 State 残留。
                "allow_semantic": state.get("allow_semantic", True),
            }

        statistic_1s = log_1s_statistic(metrics_1s)
        statistic_5s = log_5s_statistic(metrics_5s)
        log_feature = build_llm_features(statistic_1s, statistic_5s, metrics_1s)

        # P1：reference_feature 缓存，避免每轮重算
        reference_feature = _get_reference_feature(cid, pid)

    except Exception as exc:
        logger.exception("fetch_metrics failed | run_id=%s", run_id)
        return {
            **base,
            "error": f"指标拉取失败: {exc}",
            "run_id": run_id,
            "allow_semantic": state.get("allow_semantic", True),
        }

    return {
        **base,
        "run_id": run_id,
        "client_info": client_info,
        "dpdk_info": dpdk_info,
        "log_feature": log_feature,
        "reference_feature": reference_feature,
        "alert_rules": _alert_rules,
        # 显式透传 allow_semantic，不依赖 State 字段默认值，
        # 防止后续节点误写污染路由判断。
        "allow_semantic": state.get("allow_semantic", True),
    }


def node_rule_detection(state, config):
    """
    规则检测节点（第一阶段）：执行确定性规则引擎。

    基于 log_feature + reference_feature 遍历所有启用规则。
    规则级冷却在引擎内部过滤，冷却期内的规则不计入结果。
    结果写入独立字段 rule_flags，不直接写 anomaly_flags。

    用 try/except 包裹规则引擎，异常时返回 error 字段
    走 handle_error，而不是直接穿透 LangGraph 导致 invoke 抛出。
    """
    try:
        rule_flags = _run_rule_engine(
            state["log_feature"],
            state["reference_feature"],
            state["alert_rules"],
            state["client_info"].get("client_id", "unknown"),
        )
    except Exception as exc:
        logger.exception("rule_detection failed | run_id=%s", state.get("run_id"))
        return {"rule_flags": [], "error": f"规则引擎执行失败: {exc}"}

    logger.info(
        "rule_detection done | run_id=%s flags=%s", state.get("run_id"), rule_flags
    )
    return {"rule_flags": rule_flags, "error": ""}


def node_semantic_detection(state, config):
    """
    语义检测节点（第二阶段）：仅在规则引擎无异常且允许语义检测时执行。

    结果写入独立字段 semantic_flags，不直接写 anomaly_flags。
    LLM 升级意图写入 escalate_from_semantic（与 escalate_to_fault 解耦），
    由 risk_assessment 统一决策是否最终升级。
    LLM 调用失败时静默降级，不影响整体流程。
    """
    if not state.get("allow_semantic", True):
        logger.info(
            "semantic detection skipped by allow_semantic=False | run_id=%s",
            state.get("run_id"),
        )
        return {
            "semantic_flags": [],
            # 写 escalate_from_semantic 而非 escalate_to_fault，
            # 避免在 risk_assessment 之前提前污染最终升级标志。
            "escalate_from_semantic": False,
            "prompt_meta": {},
        }

    semantic_flags, escalate, prompt_meta = _run_semantic_detection(state, config)
    logger.info(
        "semantic_detection done | run_id=%s flags=%s escalate=%s",
        state.get("run_id"),
        semantic_flags,
        escalate,
    )
    return {
        "semantic_flags": semantic_flags,
        "escalate_from_semantic": escalate,
        "prompt_meta": prompt_meta,
        "error": "",
    }


def node_risk_assessment(state, config):
    """
    风险评估节点：合并 rule_flags + semantic_flags，计算告警等级。

    流程：
        1. 合并去重两路检测结果为 anomaly_flags
        2. 无异常直接返回 should_alert=False
        3. 计算最高 severity（critical > warning > info）
        4. 判断是否需要故障升级（综合 escalate_from_semantic 和规则配置）
        5. severity 级全局冷却兜底（规则级冷却已在引擎层处理）
        6. 通过后构造 alert_input 传递给 alert_generation

    escalate_to_fault 仅在此节点统一写入，
    消除 semantic_detection 和 risk_assessment 的双写竞争。
    """
    all_flags = _deduplicate(
        state.get("rule_flags", []) + state.get("semantic_flags", [])
    )

    if not all_flags:
        return {
            "anomaly_flags": [],
            "should_alert": False,
            "escalate_to_fault": False,
        }

    severity = _compute_severity(all_flags, state["alert_rules"])
    # 读 escalate_from_semantic（语义节点的独立输出），
    # 再与规则配置合并，统一写入 escalate_to_fault。
    escalate = state.get("escalate_from_semantic", False) or _has_escalation_flag(
        all_flags, state["alert_rules"]
    )
    client_id = state["client_info"].get("client_id", "unknown")

    if _in_severity_cooldown(client_id, severity):
        logger.info(
            "alert suppressed by severity cooldown | client=%s severity=%s",
            client_id,
            severity,
        )
        return {
            "anomaly_flags": all_flags,
            "should_alert": False,
            "escalate_to_fault": escalate,
        }

    _update_severity_cooldown(client_id, severity)
    return {
        "anomaly_flags": all_flags,
        "should_alert": True,
        "escalate_to_fault": escalate,
        "alert_input": {
            "log_feature": state["log_feature"],
            "severity": severity,
        },
    }


def node_alert_generation(state, config):
    """
    告警生成节点：调用 LLM 生成人类可读的告警标题和描述。

    LLM 调用失败时降级为结构化模板文本（包含关键指标数值），
    保证告警不丢失且 fallback 内容本身足够可读。

    本节点不再写 escalate_to_fault，
    edge_after_alert 读取的是 risk_assessment 已经写定的值，
    消除了"alert_generation 之后才设置升级标志"的死分支。
    """
    alert_input = state.get("alert_input", {})
    log_feature = alert_input.get("log_feature", state.get("log_feature", {}))
    severity = alert_input.get("severity", "warning")
    client_id = state["client_info"].get("client_id", "unknown")

    messages, meta = _builder.build_alert_generation(
        anomaly_summary=", ".join(state.get("anomaly_flags", [])),
        severity=severity,
        client_id=client_id,
        log_feature=log_feature,
    )

    try:
        raw = StrOutputParser().invoke(_llm.invoke(messages, config=config))
        title, description = _parse_alert_text(raw)
    except Exception as exc:
        logger.warning("alert LLM failed, using fallback text | %s", exc)
        title, description = _build_fallback_alert(
            severity, client_id, log_feature, state.get("anomaly_flags", [])
        )

    return {
        "alert": {
            "alert_id": str(uuid.uuid4()),
            "severity": severity,
            "title": title,
            "description": description,
            "client_id": client_id,
            "triggered_at": time.time(),
        },
        "prompt_meta": meta.as_log_dict() if meta else {},
        "error": "",
    }


def node_escalate_to_fault(state, config):
    """
    故障升级节点：拉取 core dump 和崩溃分析数据，切换至故障分析模式。
    拉取失败时降级为空字符串，不阻断流程。
    """
    logger.warning(
        "escalating to fault analysis | client=%s flags=%s run_id=%s",
        state["client_info"].get("client_id"),
        state.get("anomaly_flags"),
        state.get("run_id"),
    )
    return {
        "escalate_to_fault": True,
        "mode": "fault_analysis",
    }


def node_handle_error(state, config):
    """
    错误处理节点：记录错误日志并重置告警状态，终止本轮 Graph 执行。
    """
    logger.error(
        "realtime_monitor error | run_id=%s | %s",
        state.get("run_id"),
        state.get("error", "未知错误"),
    )
    return {"should_alert": False, "escalate_to_fault": False}


def cleanup_clients(client_ids: list[str]):
    """
    清理离线客户端的冷却记录和 reference 缓存。
    在客户端断开连接或主动注销时调用，防止内存泄漏。

    如需只清理特定 pid 而非整个客户端，
    请改用 cleanup_client_pid(client_id, pid)。
    当前实现清理 client_id 下所有 pid 的缓存，
    适用于客户端完全下线（所有 DPDK 进程消失）的场景。
    """
    client_set = set(client_ids)

    with _cooldown_lock:
        for k in [k for k in _cooldown_registry if k.split(":")[0] in client_set]:
            _cooldown_registry.pop(k, None)

    with _reference_cache_lock:
        for k in [k for k in _reference_cache if k.split(":")[0] in client_set]:
            _reference_cache.pop(k, None)

    logger.info("client cache cleaned | clients=%s", client_ids)


def cleanup_client_pid(client_id: str, pid: int):
    """
    精确清理单个 pid 的 reference 缓存。
    适用于客户端部分 pid 下线的场景，不影响同 client_id 下的其他 pid。
    冷却记录仍按 client_id 前缀清理（规则冷却与 pid 无关）。
    """
    cache_key = f"{client_id}:{pid}"
    with _reference_cache_lock:
        _reference_cache.pop(cache_key, None)

    with _cooldown_lock:
        for k in [k for k in _cooldown_registry if k.startswith(f"{client_id}:")]:
            _cooldown_registry.pop(k, None)

    logger.info("pid cache cleaned | client=%s pid=%s", client_id, pid)


# ── 内部实现 ──────────────────────────────────────────────────────────────────


def _get_reference_feature(cid: str, pid: int) -> dict:
    """
    获取 reference_feature，优先使用缓存（TTL=5min）。

    同时拉取 1s 和 5s 历史日志，保证与 log_feature 的字段口径一致：
    - rx_pps / rx_errors / queue_imbalance / mempool_free：来自 1s 日志
    - heap_free / heap_frag / cpu_avg：来自 5s 日志

    缓存读写通过 _reference_cache_lock 保护，
    防止多线程并发导致重复重建。
    """
    cache_key = f"{cid}:{pid}"

    with _reference_cache_lock:
        cached = _reference_cache.get(cache_key)
        if cached and (time.time() - cached["updated_at"]) < _REFERENCE_CACHE_TTL:
            logger.debug("reference_feature cache hit | client=%s pid=%s", cid, pid)
            return cached["feature"]

    logger.info("reference_feature cache miss, rebuilding | client=%s pid=%s", cid, pid)

    try:
        ref_metrics_1s = _tools["log_1s"].invoke(
            {"client_id": cid, "pid": pid, "seconds": 300}
        )
        ref_metrics_5s = _tools["log_5s"].invoke(
            {"client_id": cid, "pid": pid, "seconds": 300}
        )
        feature = build_reference_features(ref_metrics_1s, ref_metrics_5s)
    except Exception as exc:
        logger.warning("reference_feature rebuild failed, use empty | %s", exc)
        feature = {}

    with _reference_cache_lock:
        _reference_cache[cache_key] = {"feature": feature, "updated_at": time.time()}

    return feature


_FEATURE_PATH_MAP: dict[str, list[str]] = {
    "rx_pps": ["traffic", "rx_pps"],
    "tx_pps": ["traffic", "tx_pps"],
    "rx_errors": ["errors", "rx_errors"],
    "tx_errors": ["errors", "tx_errors"],
    "nombuf": ["errors", "nombuf"],
    "missed": ["errors", "missed"],
    "queue_imbalance": ["queue", "imbalance_ratio"],
    "mempool_free": ["mempool", "free_ratio"],
    "heap_free": ["heap", "free_ratio"],
    "heap_frag": ["heap", "fragmentation"],
    "cpu_avg": ["cpu", "avg_usage"],
    "risk_score": ["risk_score"],
}


def _resolve_feature(log_feature: dict, metric: str) -> float | None:
    """从 log_feature 中按 _FEATURE_PATH_MAP 路径提取指标值。"""
    path = _FEATURE_PATH_MAP.get(metric)
    if not path:
        return None
    cur = log_feature
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    try:
        return float(cur)
    except Exception:
        return None


def _run_rule_engine(
    log_feature: dict,
    reference_feature: dict,
    rules,
    client_id: str,
) -> list[str]:
    """
    确定性规则引擎。

    规则级冷却在此处过滤，冷却期内的规则直接跳过。
    使用规则自身配置的 cooldown_sec，粒度为 client_id:rule_id。

    冷却检查与写入都通过 _in_rule_cooldown /
    _update_rule_cooldown 加锁操作，消除多线程 TOCTOU 窗口。
    """
    flags = []
    for rule in rules:
        if not rule.enabled:
            continue

        if _in_rule_cooldown(client_id, rule.id, rule.cooldown_sec):
            logger.debug("rule in cooldown | id=%s client=%s", rule.id, client_id)
            continue

        value = _resolve_feature(log_feature, rule.metric)
        if value is None:
            continue

        ref_value = reference_feature.get(rule.metric) if reference_feature else None

        if _evaluate_condition(value, rule.condition, rule.threshold, ref_value):
            flags.append(rule.id)
            _update_rule_cooldown(client_id, rule.id)
            logger.debug(
                "rule triggered | id=%s value=%s ref=%s", rule.id, value, ref_value
            )

    return flags


def _run_semantic_detection(state, config) -> tuple[list[str], bool, dict]:
    """
    LLM 语义检测，仅在规则无异常时调用。
    失败时静默降级返回空结果。

    返回值中的 bool 表示 LLM 判定是否需要升级（escalate_from_semantic），
    而非直接写 escalate_to_fault。
    """
    try:
        messages, meta = _builder.build_anomaly_detection(
            log_feature=state["log_feature"],
            reference_feature=state["reference_feature"],
            alert_rules=state["alert_rules"],
        )
        raw = StrOutputParser().invoke(_llm.invoke(messages, config=config))
        flags, escalate = _parse_semantic_output(raw)
        return flags, escalate, meta.as_log_dict()
    except Exception as exc:
        logger.warning("semantic detection failed, rule-only mode | %s", exc)
        return [], False, {}


def _evaluate_condition(
    value: float, condition: str, threshold: float, ref_value=None
) -> bool:
    """执行单条规则的条件判断，支持绝对阈值和参考值对比。"""
    match condition:
        case "gt":
            return value > threshold
        case "lt":
            return value < threshold
        case "gte":
            return value >= threshold
        case "lte":
            return value <= threshold
        case "eq":
            return value == threshold
        case "ref_ratio" if ref_value not in (None, 0):
            return (value / ref_value) > threshold
        case "ref_delta" if ref_value is not None:
            return (value - ref_value) > threshold
    return False


def _parse_semantic_output(raw: str) -> tuple[list[str], bool]:
    """解析 LLM 语义检测输出，提取 ANOMALIES 和 ESCALATE 字段。"""
    flags = []
    if m := re.search(r"ANOMALIES:\s*(.+)", raw, re.IGNORECASE):
        raw_flags = m.group(1).strip()
        if raw_flags.upper() != "NONE":
            flags = [f.strip() for f in raw_flags.split(",") if f.strip()]
    escalate = bool(re.search(r"ESCALATE:\s*yes", raw, re.IGNORECASE))
    return flags, escalate


def _parse_alert_text(raw: str) -> tuple[str, str]:
    """解析 LLM 告警生成输出，提取 TITLE 和 DESCRIPTION。"""
    title = description = ""
    if m := re.search(r"TITLE:\s*(.+)", raw, re.IGNORECASE):
        title = m.group(1).strip()
    if m := re.search(r"DESCRIPTION:\s*([\s\S]+)", raw, re.IGNORECASE):
        description = m.group(1).strip()
    return title or raw[:80], description or raw


def _build_fallback_alert(
    severity: str, client_id: str, log_feature: dict, flags: list
) -> tuple[str, str]:
    """
    LLM 告警生成失败时的结构化 fallback。
    基于 log_feature 关键指标生成可读文本，而非仅输出规则ID。
    """
    traffic = log_feature.get("traffic", {})
    errors = log_feature.get("errors", {})
    mempool = log_feature.get("mempool", {})
    heap = log_feature.get("heap", {})
    cpu = log_feature.get("cpu", {})

    title = f"[{severity.upper()}] DPDK 异常 — {client_id}"
    description = (
        f"触发规则: {', '.join(flags)}\n"
        f"流量: RX {traffic.get('rx_pps', 0):.1f} pps / "
        f"TX {traffic.get('tx_pps', 0):.1f} pps\n"
        f"错误: RX错误={errors.get('rx_errors', 0)} "
        f"MBUF不足={errors.get('nombuf', 0)} "
        f"丢包={errors.get('missed', 0)}\n"
        f"内存池空闲: {mempool.get('free_ratio', 1.0):.1%} | "
        f"堆内存空闲: {heap.get('free_ratio', 1.0):.1%}\n"
        f"CPU均值: {cpu.get('avg_usage', 0.0):.1%}"
    )
    return title, description


def _compute_severity(flags: list, rules) -> str:
    """从触发规则中提取最高告警等级，优先级 critical > warning > info。"""
    rule_map = {r.id: r for r in rules}
    severities = {rule_map[f].severity for f in flags if f in rule_map}
    return next(
        (lv for lv in ("critical", "warning", "info") if lv in severities), "info"
    )


def _has_escalation_flag(flags: list, rules) -> bool:
    """判断触发规则中是否存在需要故障升级的规则。"""
    rule_map = {r.id: r for r in rules}
    return any(rule_map.get(f) and rule_map[f].escalate_to_fault for f in flags)


# ── 规则级冷却（细粒度）──────────────────────────────────────────────────────


def _in_rule_cooldown(client_id: str, rule_id: str, cooldown_sec: int) -> bool:
    """
    判断指定规则是否处于冷却期（粒度：client_id:rule_id）。

    加锁读取，与 _update_rule_cooldown 共享同一把锁，
    消除检查-触发之间的 TOCTOU 窗口。
    """
    key = f"{client_id}:rule:{rule_id}"
    with _cooldown_lock:
        return (time.time() - _cooldown_registry.get(key, 0.0)) < cooldown_sec


def _update_rule_cooldown(client_id: str, rule_id: str):
    """规则触发后写入冷却时间戳（加锁）。"""
    with _cooldown_lock:
        _cooldown_registry[f"{client_id}:rule:{rule_id}"] = time.time()


# ── severity 级冷却（粗粒度兜底）────────────────────────────────────────────


def _in_severity_cooldown(client_id: str, severity: str) -> bool:
    """判断指定 severity 等级是否处于全局冷却期（加锁）。"""
    key = f"{client_id}:severity:{severity}"
    with _cooldown_lock:
        return (
            time.time() - _cooldown_registry.get(key, 0.0)
        ) < settings.alert_cooldown_sec


def _update_severity_cooldown(client_id: str, severity: str):
    """更新 severity 级全局冷却时间戳（加锁）。"""
    with _cooldown_lock:
        _cooldown_registry[f"{client_id}:severity:{severity}"] = time.time()


def _deduplicate(flags: list) -> list:
    """对告警标志列表去重，保持原始顺序。"""
    seen: set[str] = set()
    return [f for f in flags if not (f in seen or seen.add(f))]