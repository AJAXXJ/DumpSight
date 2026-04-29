from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from typing import Any

from agent.graphs.state import DPDKDiagnosisState


class ReportFormatter:
    """
    用法:
        formatter = ReportFormatter()
        md   = formatter.to_markdown(state)
        data = formatter.to_json(state)
        txt  = formatter.to_plain(state)
    """

    def to_markdown(self, state: DPDKDiagnosisState) -> str:
        """
        生成完整的 Markdown 故障报告。
        各 section 独立渲染，缺失字段优雅降级为占位文本。
        """
        is_fault = bool(state.get("core_info"))

        sections = [
            _md_header(state),
            _md_summary(state),
            _md_environment(state),
            _md_crash_stack(state) if is_fault else _md_escalate_result(state),
            _md_root_cause(state),
            _md_repair_steps(state),
            _md_log_feature(state),
            _md_similar_cases(state),
            _md_prompt_meta(state),
            _md_footer(state),
        ]
        return "\n\n".join(s for s in sections if s.strip())


def _md_header(state: DPDKDiagnosisState) -> str:
    ts = _iso_now()
    rid = state.get("run_id", "N/A")
    return f"# DPDK 故障分析报告\n\n> 生成时间: {ts}  |  Run ID: `{rid}`\n"


def _md_summary(state: DPDKDiagnosisState) -> str:
    conf = state.get("confidence", "medium")
    badge = _confidence_badge(conf)
    client = _get(state, "client_info", "client_id", default="N/A")
    ver = _get(state, "client_info", "environment", "version", default="N/A")
    crash_timestamp = _get(state, "core_info", "core_timestamp")
    crash_time = datetime.fromtimestamp(crash_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return (
        "## 摘要\n\n"
        f"| 字段 | 值 |\n"
        f"|------|----|\n"
        f"| 客户端 | `{client}` |\n"
        f"| DPDK 版本 | `{ver}` |\n"
        f"| 诊断置信度 | {badge} |\n"
        f"| 崩溃时间 | {crash_time} |\n"
        f"| 匹配历史案例 | {len(state.get('retrieved_cases', []))} 条 |\n\n"
    )


def _md_environment(state: DPDKDiagnosisState) -> str:
    # meta
    hostname = _get(state, "client_info", "environment", "hostname", default="N/A")
    os = _get(state, "client_info", "environment", "os", default="N/A")

    # hugepage
    hugepage = _get(state, "client_info", "environment", "hugepage", default="N/A")

    def calculate_hugepage_memory(hugepages_data):
        total_hugepages = hugepages_data.get("HugePages_Total", 0)
        hugepage_size_kb = hugepages_data.get("Hugepagesize_kB", 0)

        total_hugepage_memory_kb = total_hugepages * hugepage_size_kb  # 以 KB 为单位
        total_hugepage_memory_mb = total_hugepage_memory_kb / 1024  # 转换为 MB

        return total_hugepage_memory_mb

    total_hugepage_memory = calculate_hugepage_memory(hugepage)

    # cpu
    lscpu = _get(state, "core_info", "context", "lscpu", default="N/A")

    ports = lscpu["Socket(s)"]

    logical_cores = (
        int(ports) * int(lscpu["Core(s) per socket"]) * int(lscpu["Thread(s) per core"])
    )

    memory_channels = lscpu["NUMA node(s)"]

    return (
        "## 运行环境\n\n"
        f"| 字段       | 值               |\n"
        f"|------------|------------------|\n"
        f"| 主机名     | {hostname} |\n"
        f"| 操作系统   | {os} |\n"
        f"| 端口数     | {ports} |\n"
        f"| 逻辑核心   | {logical_cores} |\n"
        f"| 内存通道   | {memory_channels} |\n"
        f"| 大页内存   | {total_hugepage_memory} MB |\n\n"
    )


def parse_call_chain_graph(state):
        # 获取崩溃函数
        crash_function = _get(
            state,
            "core_info",
            "meta",
            "parsed_gdb_output",
            "call_chain_graph",
            "crash_function",
            default="N/A",
        )

        # 获取调用链
        call_graph = _get(
            state,
            "core_info",
            "meta",
            "parsed_gdb_output",
            "call_chain_graph",
            "call_graph",
            default="N/A",
        )

        # 获取主线程的调用链
        main_thread = _get(
            state,
            "core_info",
            "meta",
            "parsed_gdb_output",
            "call_chain_graph",
            "main_thread",
            default="N/A",
        )

        # 提取主线程的调用堆栈
        main_thread_stack = []
        for frame in main_thread.get("callstack", []):
            main_thread_stack.append(frame.get("raw", "N/A"))

        # 提取所有线程的堆栈信息
        threads_stack = {}
        threads = state.get("call_chain_graph", {}).get("threads", {})
        for tid, thread in threads.items():
            thread_stack = []
            for frame in thread.get("callstack", []):
                thread_stack.append(frame.get("raw", "N/A"))
            threads_stack[tid] = thread_stack

        # 提取调用链
        call_chain = []
        for caller, callees in call_graph.items():
            for callee in callees:
                call_chain.append(f"{caller} -> {callee}")


        return {
            "crash_function": crash_function,
            "main_thread_stack": main_thread_stack,
            "threads_stack": threads_stack,
            "call_chain": call_chain,
        }

def _md_crash_stack(state: DPDKDiagnosisState) -> str:
    parsed_data = parse_call_chain_graph(state)

    crash_function = parsed_data.get("crash_function", "N/A")
    main_thread_stack = "\n".join(parsed_data.get("main_thread_stack", []))

    threads_report = ""
    for tid, thread_stack in parsed_data.get("threads_stack", {}).items():
        threads_report += (
            f"\n**线程 {tid} 堆栈**:\n```\n" + "\n".join(thread_stack) + "\n```\n"
        )

    call_chain = "\n" + "\n".join(parsed_data.get("call_chain", [])) + "\n"
    
    lines = [
        "## 崩溃信息报告",
        "",
        f"> {state['description']}" if state['description'] else "",
        "",
        f"**崩溃函数**: `{crash_function}`",
        "",
        "**主线程堆栈**:",
        "```",
        main_thread_stack,
        "```",
        threads_report,
        "**调用链**:",
        "```",
        call_chain,
        "```",
    ]

    
    return "\n".join(lines)


def _md_escalate_result(state: DPDKDiagnosisState) -> str:
    """
    渲染预警升级的异常检测结果（非 crash 场景）。
    从 state["escalate_result"] 中提取 monitor Graph 输出信息生成 Markdown。

    escalate_result 实际结构（来自 monitor Graph result）：
    {
        "alert": {
            "severity":    "critical/warning/info",
            "title":       "告警标题",
            "description": "告警描述",
            "triggered_at": float,
        },
        "anomaly_flags":  ["RULE_ID_1", "RULE_ID_2", ...],  # 规则ID字符串列表
        "rule_flags":     ["RULE_ID_1", ...],
        "semantic_flags": ["SEMANTIC_FLAG_1", ...],
        "log_feature": {
            "risk_score":   int,
            "risk_level":   "low/medium/high/critical",
            "risk_breakdown": {...},
            "insight":      [...],
            "risk":         [...],
        },
    }
    """
    result = state.get("escalate_result") or {}
    alert = result.get("alert") or {}
    log_feature = result.get("log_feature") or {}

    severity = alert.get("severity", "unknown")
    title = alert.get("title", "")
    description = alert.get("description", "")
    triggered_at = alert.get("triggered_at")

    anomaly_flags = result.get("anomaly_flags") or []
    rule_flags = result.get("rule_flags") or []
    semantic_flags = result.get("semantic_flags") or []

    risk_score = log_feature.get("risk_score", 0)
    risk_level = log_feature.get("risk_level", "unknown")
    risk_breakdown = log_feature.get("risk_breakdown") or {}
    insight = log_feature.get("insight") or []
    risk_tags = log_feature.get("risk") or []

    # 时间格式化
    triggered_str = ""
    if triggered_at:
        import datetime

        triggered_str = datetime.datetime.fromtimestamp(triggered_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    md = ["## ⚠️ 预警升级信息"]

    # 告警标题与等级
    if title:
        md.append(f"\n**{title}**")
    md.append(f"- **告警等级**: `{severity.upper()}`")
    if triggered_str:
        md.append(f"- **触发时间**: {triggered_str}")

    # 综合风险
    md.append(f"\n### 风险评估")
    md.append(f"- **风险评分**: {risk_score} / 100")
    md.append(f"- **风险等级**: `{risk_level}`")

    if risk_breakdown:
        md.append("- **风险明细**:")
        for dim, score in risk_breakdown.items():
            md.append(f"  - {dim}: {score} 分")

    # 异常标志
    md.append(f"\n### 异常标志")
    if rule_flags:
        md.append("- **规则触发**:")
        for flag in rule_flags:
            md.append(f"  - `{flag}`")
    if semantic_flags:
        md.append("- **语义检测**:")
        for flag in semantic_flags:
            md.append(f"  - `{flag}`")
    if not anomaly_flags:
        md.append("- 无异常标志")

    # 系统洞察
    if insight:
        md.append(f"\n### 系统洞察")
        for item in insight:
            md.append(f"- {item}")

    # 风险标签
    if risk_tags:
        md.append(f"\n### 风险标签")
        for tag in risk_tags:
            md.append(f"- `{tag}`")

    # 告警描述
    if description:
        md.append(f"\n### 告警详情")
        md.append(description)

    return "\n".join(md)


def _md_root_cause(state: DPDKDiagnosisState) -> str:
    cause = state.get("root_cause", "").strip()
    if not cause:
        return "## 根因分析\n\n_未能确定根因，请补充更多上下文后重试。_"

    conf_cn = _confidence_cn(state.get("confidence", "medium"))
    return "## 根因分析\n\n" f"> 置信度：**{conf_cn}**\n\n" + cause


def _md_repair_steps(state: DPDKDiagnosisState) -> str:
    steps = state.get("repair_steps", [])
    if not steps:
        return "## 修复建议\n\n_暂无可操作建议。_"
    items = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
    return f"## 修复建议\n\n{items}"


def _md_log_feature(state: DPDKDiagnosisState) -> str:
    log_feature = state.get("log_feature")
    if not log_feature:
        return "## 日志解析\n\n_暂无日志解析。_"

    sys = log_feature.get("system_status", {})
    window = log_feature.get("window", {})
    traffic = log_feature.get("traffic", {})
    queue = log_feature.get("queue", {})
    mem = log_feature.get("mempool", {})
    heap = log_feature.get("heap", {})
    cpu = log_feature.get("cpu", {})
    err = log_feature.get("errors", {})
    risk_breakdown = log_feature.get("risk_breakdown", {})
    insights = log_feature.get("insight", [])

    lines = [
        "## 日志解析\n",
        "| 维度 | 指标 | 值 |",
        "|------|------|----|",
        f"| 系统 | 存活状态 | {'正常' if sys.get('is_alive') else '异常'} |",
        f"| 时间窗口 | 1s / 5s | {window.get('1s', 0):.2f}s / {window.get('5s', 0):.2f}s |",
        f"| 流量 | RX/TX PPS | {traffic.get('rx_pps', 0):.2f} / {traffic.get('tx_pps', 0):.2f} |",
        f"| 流量 | 等级/趋势/稳定性 | {traffic.get('traffic_level')} / {traffic.get('trend')} / {traffic.get('stability')} |",
        f"| 队列 | 不均衡比例 / 状态 | {queue.get('imbalance_ratio', 0):.4f} / {queue.get('status')} |",
        f"| Mempool | 空闲率 / 状态 / 趋势 | {mem.get('free_ratio', 0):.4f} / {mem.get('status')} / {mem.get('trend')} |",
        f"| Heap | 空闲率 / 碎片率 / 状态 | {heap.get('free_ratio', 0):.4f} / {heap.get('fragmentation', 0):.4f} / {heap.get('status')} |",
        f"| CPU | 均值 / 状态 / 趋势 / 热核 | {cpu.get('avg_usage', 0):.2f} / {cpu.get('status')} / {cpu.get('trend')} / {cpu.get('hot_lcore')} |",
        f"| 错误 | RX/TX/NoMBUF/Missed | {err.get('rx_errors')} / {err.get('tx_errors')} / {err.get('nombuf')} / {err.get('missed')} |",
        f"| 风险 | 等级 / 分数 | {log_feature.get('risk_level')} / {log_feature.get('risk_score')} |",
    ]

    if risk_breakdown:
        breakdown_str = " / ".join(f"{k}:{v}" for k, v in risk_breakdown.items())
        lines.append(f"| 风险拆解 | - | {breakdown_str} |")

    risk_tags = log_feature.get("risk", [])
    if risk_tags:
        lines.append(f"| 风险标签 | - | {', '.join(risk_tags)} |")

    if insights:
        lines.append("\n**系统洞察**\n")
        lines.extend(f"- {i}" for i in insights)

    return "\n".join(lines)


def _md_escalate_result(state: DPDKDiagnosisState) -> str:
    result = state.get("escalate_result") or {}
    alert = result.get("alert") or {}
    log_feature = result.get("log_feature") or {}

    severity = alert.get("severity", "unknown")
    title = alert.get("title", "")
    description = alert.get("description", "")
    triggered_at = alert.get("triggered_at")
    triggered_str = (
        datetime.fromtimestamp(triggered_at).strftime("%Y-%m-%d %H:%M:%S")
        if triggered_at else ""
    )

    rule_flags = result.get("rule_flags") or []
    semantic_flags = result.get("semantic_flags") or []
    risk_score = log_feature.get("risk_score", 0)
    risk_level = log_feature.get("risk_level", "unknown")
    risk_breakdown = log_feature.get("risk_breakdown") or {}
    insight = log_feature.get("insight") or []
    risk_tags = log_feature.get("risk") or []

    lines = ["## 预警升级信息\n"]

    lines += [
        "| 字段 | 值 |",
        "|------|----|",
        f"| 告警等级 | `{severity.upper()}` |",
    ]
    if title:
        lines.append(f"| 标题 | {title} |")
    if triggered_str:
        lines.append(f"| 触发时间 | {triggered_str} |")
    lines += [
        f"| 风险评分 | {risk_score} / 100 |",
        f"| 风险等级 | `{risk_level}` |",
    ]

    if risk_breakdown:
        lines.append(f"| 风险明细 | {' / '.join(f'{k}:{v}' for k, v in risk_breakdown.items())} |")

    if rule_flags:
        lines.append(f"| 规则触发 | {', '.join(f'`{f}`' for f in rule_flags)} |")
    if semantic_flags:
        lines.append(f"| 语义检测 | {', '.join(f'`{f}`' for f in semantic_flags)} |")
    if risk_tags:
        lines.append(f"| 风险标签 | {', '.join(f'`{t}`' for t in risk_tags)} |")

    if insight:
        lines.append("\n**系统洞察**\n")
        lines.extend(f"- {i}" for i in insight)

    if description:
        lines.append(f"\n**告警详情**\n\n{description}")

    return "\n".join(lines)


def _md_similar_cases(state: DPDKDiagnosisState) -> str:
    cases = state.get("retrieved_cases", [])
    if not cases:
        return ""

    rows = "\n".join(
        f"| `{c.get('case_id','?')}` "
        f"| `{c.get('description','?')}` "
        f"| {c.get('root_cause','')[:60]} "
        f"| {c.get('score', 0):.2f} "
        f"| {'；'.join(c.get('repair_steps') or [])[:60]} |"
        for c in cases
    )
    return (
        "## 参考历史案例\n\n"
        "| 案例 ID | 描述 | 根因  | 相似度  | 修复步骤 |\n"
        "|---------|------|------|--------|----------|\n" + rows
    )


def _md_prompt_meta(state: DPDKDiagnosisState) -> str:
    meta = state.get("prompt_meta", {})
    if not meta:
        return ""
    return (
        "<details>\n<summary>Prompt 元数据</summary>\n\n"
        f"```json\n{json.dumps(meta, ensure_ascii=False, indent=2)}\n```\n\n"
        "</details>"
    )


def _md_footer(state: DPDKDiagnosisState) -> str:
    return (
        "---\n\n"
        "_本报告由 DPDK 故障诊断系统自动生成，"
        "最终修复方案请结合实际环境由工程师确认。_\n"
    )


def _get(state: dict, *keys: str, default: Any = None) -> Any:
    """多层嵌套安全取值。"""
    cur = state
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
        if cur is None:
            return default
    return cur


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _confidence_cn(conf: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(conf, "中")


def _confidence_badge(conf: str) -> str:
    """Markdown 徽章风格的置信度标记。"""
    mapping = {
        "high": "![high](https://img.shields.io/badge/置信度-高-brightgreen)",
        "medium": "![medium](https://img.shields.io/badge/置信度-中-yellow)",
        "low": "![low](https://img.shields.io/badge/置信度-低-red)",
    }
    return mapping.get(conf, _confidence_cn(conf))


_default_formatter: ReportFormatter | None = None


def get_formatter() -> ReportFormatter:
    global _default_formatter
    if _default_formatter is None:
        _default_formatter = ReportFormatter()
    return _default_formatter
