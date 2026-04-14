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
        sections = [
            _md_header(state),
            _md_summary(state),
            _md_environment(state),
            _md_crash_stack(state),
            _md_root_cause(state),
            _md_repair_steps(state),
            _md_similar_cases(state),
            _md_prompt_meta(state),
            _md_footer(state),
        ]
        return "\n\n".join(s for s in sections if s.strip())


    def to_json(self, state: DPDKDiagnosisState, *, indent: int = 2) -> str:

        def parse_call_chain_graph(state):
            crash_function = _get(
                state, "core_info", "meta", "parsed_gdb_output",
                "call_chain_graph", "crash_function", default="N/A",
            )
            call_graph = _get(
                state, "core_info", "meta", "parsed_gdb_output",
                "call_chain_graph", "call_graph", default={},
            )
            main_thread = _get(
                state, "core_info", "meta", "parsed_gdb_output",
                "call_chain_graph", "main_thread", default={},
            )
            main_thread_stack = [
                frame.get("raw", "N/A")
                for frame in main_thread.get("callstack", [])
            ]
            call_chain = [
                f"{caller} -> {callee}"
                for caller, callees in (call_graph.items() if isinstance(call_graph, dict) else [])
                for callee in callees
            ]
            return {
                "crash_function": crash_function,
                "main_thread_stack": main_thread_stack,
                "call_chain": call_chain,
            }

        parsed = parse_call_chain_graph(state)

        # 环境信息
        lscpu = _get(state, "core_info", "context", "lscpu", default="N/A")

        ports = lscpu["Socket(s)"]

        logical_cores = int(ports) * int(lscpu["Core(s) per socket"]) * int(lscpu["Thread(s) per core"])

        memory_channels = lscpu["NUMA node(s)"]


        hugepage = _get(state, "client_info", "environment", "hugepage", default={})
        total_hugepage_mb = (
            hugepage.get("HugePages_Total", 0) * hugepage.get("Hugepagesize_kB", 0) / 1024
            if isinstance(hugepage, dict) else 0
        )

        payload = {
            "run_id": state.get("run_id"),
            "generated_at": _iso_now(),
            "client": {
                "client_id":    _get(state, "client_info", "client_id"),
                "dpdk_version": _get(state, "client_info", "environment", "version"),
                "os":           _get(state, "client_info", "os"),
                "hostname":     _get(state, "client_info", "hostname"),
            },
            "environment": {
                "ports":             ports,
                "logical_cores":     logical_cores,
                "memory_channels":   memory_channels,
                "hugepage_total_mb": round(total_hugepage_mb, 2),
            },
            "diagnosis": {
                "root_cause":   state.get("root_cause", ""),
                "confidence":   state.get("confidence", "medium"),
                "call_chain":   parsed["call_chain"],
                "repair_steps": state.get("repair_steps", []),
            },
            "crash": {
                "crash_function":    parsed["crash_function"],
                "main_thread_stack": parsed["main_thread_stack"],
            },
            "similar_cases": [
                {
                    "case_id":     c.get("case_id"),
                    "root_cause":  c.get("root_cause"),
                    "score":       round(c.get("score", 0.0), 4),
                    "repair_steps": c.get("repair_steps"),
                }
                for c in state.get("retrieved_cases", [])
            ],
            "prompt_meta": state.get("prompt_meta", {}),
        }
        return json.dumps(payload, ensure_ascii=False, indent=indent)


    def to_plain(self, state: DPDKDiagnosisState, *, width: int = 80) -> str:
        lines: list[str] = []
        sep = "=" * width

        def section(title: str, body: str) -> None:
            lines.append(sep)
            lines.append(f"  {title.upper()}")
            lines.append(sep)
            for para in body.strip().splitlines():
                lines.append(textwrap.fill(para, width=width) if para.strip() else "")
            lines.append("")

        # 环境信息
        lscpu = _get(state, "core_info", "context", "lscpu", default="N/A")

        ports = lscpu["Socket(s)"]

        logical_cores = int(ports) * int(lscpu["Core(s) per socket"]) * int(lscpu["Thread(s) per core"])

        memory_channels = lscpu["NUMA node(s)"]
        hugepage = _get(state, "client_info", "environment", "hugepage", default={})
        total_hugepage_mb = (
            hugepage.get("HugePages_Total", 0) * hugepage.get("Hugepagesize_kB", 0) / 1024
            if isinstance(hugepage, dict) else 0
        )

        # crash 解析
        crash_function = _get(
            state, "core_info", "meta", "parsed_gdb_output",
            "call_chain_graph", "crash_function", default="N/A",
        )
        call_graph = _get(
            state, "core_info", "meta", "parsed_gdb_output",
            "call_chain_graph", "call_graph", default={},
        )
        main_thread = _get(
            state, "core_info", "meta", "parsed_gdb_output",
            "call_chain_graph", "main_thread", default={},
        )
        main_thread_stack = [
            frame.get("raw", "N/A")
            for frame in main_thread.get("callstack", [])
        ]
        call_chain_list = [
            f"{caller} -> {callee}"
            for caller, callees in (call_graph.items() if isinstance(call_graph, dict) else [])
            for callee in callees
        ]

        section(
            "DPDK 故障分析报告",
            f"Run ID   : {state.get('run_id', 'N/A')}\n"
            f"生成时间 : {_iso_now()}\n"
            f"客户端   : {_get(state, 'client_info', 'client_id', default='N/A')}\n"
            f"DPDK 版本: {_get(state, 'client_info', 'environment', 'version', default='N/A')}",
        )

        section(
            "运行环境",
            f"主机名   : {_get(state, 'client_info', 'hostname', default='N/A')}\n"
            f"操作系统 : {_get(state, 'client_info', 'os', default='N/A')}\n"
            f"端口数     : {ports}\n"
            f"逻辑核心 : {logical_cores}\n"
            f"内存通道 : {memory_channels}\n"
            f"大页内存 : {total_hugepage_mb:.2f} MB",
        )

        section(
            "根因分析",
            f"置信度: {_confidence_cn(state.get('confidence', 'medium'))}\n\n"
            + (state.get("root_cause") or "未确定"),
        )

        if crash_function != "N/A" or main_thread_stack:
            stack_text = (
                f"崩溃函数 : {crash_function}\n"
                f"主线程堆栈:\n" + "\n".join(f"  {f}" for f in main_thread_stack[:30])
            )
            section("崩溃信息", stack_text)

        if call_chain_list:
            section(
                "调用链",
                "\n".join(f"  {i+1}. {f}" for i, f in enumerate(call_chain_list)),
            )

        if state.get("repair_steps"):
            section(
                "修复建议",
                "\n".join(f"  {i+1}. {s}" for i, s in enumerate(state["repair_steps"])),
            )

        if state.get("retrieved_cases"):
            body = "\n".join(
                f"  [{c.get('case_id','?')}] {c.get('root_cause','')} "
                f"(相似度 {c.get('score',0):.2f})"
                for c in state["retrieved_cases"]
            )
            section("参考历史案例", body)

        lines.append(sep)
        return "\n".join(lines)


def _md_header(state: DPDKDiagnosisState) -> str:
    ts = _iso_now()
    rid = state.get("run_id", "N/A")
    return f"# DPDK 故障分析报告\n\n> 生成时间: {ts}  |  Run ID: `{rid}`\n"


def _md_summary(state: DPDKDiagnosisState) -> str:
    conf = state.get("confidence", "medium")
    badge = _confidence_badge(conf)
    client = _get(state, "client_info", "client_id", default="N/A")
    ver = _get(state, "client_info", "environment", "version", default="N/A")

    return (
        "## 摘要\n\n"
        f"| 字段 | 值 |\n"
        f"|------|----|\n"
        f"| 客户端 | `{client}` |\n"
        f"| DPDK 版本 | `{ver}` |\n"
        f"| 诊断置信度 | {badge} |\n"
        f"| 匹配历史案例 | {len(state.get('retrieved_cases', []))} 条 |\n\n"
    )


def _md_environment(state: DPDKDiagnosisState) -> str:
    client_info = state.get("client_info", {})

    # meta
    hostname = client_info.get("hostname", "N/A")
    os = client_info.get("os", "N/A")

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

    logical_cores = int(ports) * int(lscpu["Core(s) per socket"]) * int(lscpu["Thread(s) per core"])

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


def _md_crash_stack(state: DPDKDiagnosisState) -> str:
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
            "call_chain": call_chain
        }

    parsed_data = parse_call_chain_graph(state)

    crash_function = parsed_data.get("crash_function", "N/A")
    main_thread_stack = "\n".join(parsed_data.get("main_thread_stack", []))
    
    # 添加所有线程堆栈
    threads_report = ""
    for tid, thread_stack in parsed_data.get("threads_stack", {}).items():
        threads_report += f"\n**线程 {tid} 堆栈**:\n```\n" + "\n".join(thread_stack) + "\n```\n"
    
    call_chain = "\n".join(parsed_data.get("call_chain", []))
    
    return f"""
    ## 崩溃信息报告
    
    **崩溃函数**: `{crash_function}`
    
    **主线程堆栈**:
    ```
    {main_thread_stack}
    ```
    
    {threads_report}

    **调用链**:
    ```
    {call_chain}
    ```
    """


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


def _md_similar_cases(state: DPDKDiagnosisState) -> str:
    cases = state.get("retrieved_cases", [])
    if not cases:
        return ""

    rows = "\n".join(
        f"| `{c.get('case_id','?')}` "
        f"| {c.get('root_cause','')[:60]} "
        f"| {c.get('score', 0):.2f} "
        f"| {c.get('fix_summary','')[:60]} |"
        for c in cases
    )
    return (
        "## 参考历史案例\n\n"
        "| 案例 ID | 根因 | 相似度 | 修复摘要 |\n"
        "|---------|------|--------|----------|\n" + rows
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
