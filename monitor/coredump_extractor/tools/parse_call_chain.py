import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any


@dataclass
class CallNode:
    """
    调用链节点（execution order 中的位置）

    Attributes:
        name: 标准化函数名
        gdb_depth: GDB backtrace 中的原始 #index（保留用于调试）
        exec_depth: 执行深度（0=root, max=crash）
        raw: 原始 GDB frame 字符串
        source: 源文件位置
        address: 指令地址
    """

    name: str
    gdb_depth: int  # GDB #index（#0=crash）
    exec_depth: int  # 执行深度（0=root）
    raw: str = ""
    source: Optional[str] = None
    address: Optional[str] = None

    def to_dict(self):
        return {
            "name": self.name,
            "gdb_depth": self.gdb_depth,
            "exec_depth": self.exec_depth,
            "raw": self.raw,
            "source": self.source,
            "address": self.address,
        }


@dataclass
class CallEdge:
    """
    有向调用边（execution order）

    caller → callee 表示执行流向
    """

    caller: str  # 调用者（执行序靠前）
    callee: str  # 被调用者（执行序靠后）
    weight: int = 1

    def to_dict(self):
        return {
            "caller": self.caller,
            "callee": self.callee,
            "weight": self.weight,
        }


@dataclass
class ThreadChain:
    """
    单线程调用链（canonical representation）

    Attributes:
        callstack: 按 execution order 排列（root → crash）
        edges: 调用边（caller → callee）
        crash_func: 崩溃函数（callstack[-1]）
    """

    tid: str
    callstack: List[CallNode] = field(default_factory=list)
    edges: List[CallEdge] = field(default_factory=list)
    crash_func: Optional[str] = None

    def __post_init__(self):
        """确保 crash_func 与 callstack 一致"""
        if self.callstack and not self.crash_func:
            self.crash_func = self.callstack[-1].name

    def to_dict(self):
        return {
            "tid": self.tid,
            "callstack": [n.to_dict() for n in self.callstack],
            "edges": [e.to_dict() for e in self.edges],
            "crash_func": self.crash_func,
        }


@dataclass
class CallChainResult:
    """
    最终解析结果（所有数据遵循 execution order）
    """

    crash_function: str
    crash_signature: str  # crash + N 层 caller 的特征串
    main_thread: ThreadChain
    threads: Dict[str, ThreadChain] = field(default_factory=dict)
    common_frames: List[str] = field(default_factory=list)
    call_graph: Dict[str, Set[str]] = field(default_factory=dict)
    parse_warnings: list[dict] = field(default_factory=list)

    def to_dict(self):
        return {
            "crash_function": self.crash_function,
            "crash_signature": self.crash_signature,
            "main_thread": self.main_thread.to_dict(),
            "threads": {k: v.to_dict() for k, v in self.threads.items()},
            "common_frames": self.common_frames,
            "call_graph": {
                k: list(v) for k, v in self.call_graph.items()  # ❗ set → list
            },
        }


_FRAME_PATTERNS = [
    # 模式1：标准格式，参数用非贪婪跳过，源文件在最后
    re.compile(
        r"^#(?P<idx>\d+)\s+"
        r"(?P<addr>0x[0-9a-fA-F]+)?\s*"
        r"(?:in\s+)?"
        r"(?P<func>[^\s(]+)"
        r"(?:\s*\(.*?\))?"          # 非贪婪匹配参数，允许内部有任意内容
        r"(?:\s+at\s+(?P<src>\S+:\d+))?",
        re.DOTALL,
    ),
    # 模式2：from 共享库格式
    re.compile(
        r"^#(?P<idx>\d+)\s+"
        r"(?P<func>[^\s(]+)"
        r"(?:\s*\(.*?\))?"
        r"(?:\s+from\s+(?P<src>\S+))?",
        re.DOTALL,
    ),
]

_INVALID_FUNCS: Set[str] = {"??", "unknown", "", "_start", "__libc_start_main"}


def _parse_frame(raw: str) -> Optional[Tuple[int, str, Optional[str], Optional[str]]]:
    """
    解析单个 GDB frame → (gdb_index, func_name, source, address)

    返回元组而非 CallNode，因为 exec_depth 需要在全局翻转后才能确定
    """
    line = raw.strip()
    if not line.startswith("#"):
        return None

    for pattern in _FRAME_PATTERNS:
        m = pattern.match(line)
        if not m:
            continue

        groups = m.groupdict()
        func = _normalize_func(groups.get("func") or "")
        if isinstance(func, list):
            func = func[0] if func else "unknown"

        if not func or func in _INVALID_FUNCS:
            return None

        return (
            int(groups.get("idx", 0)),
            func,
            groups.get("src"),
            groups.get("addr"),
        )

    return None


def _normalize_func(raw_func: str) -> str:
    """标准化函数名"""
    func = raw_func.strip()
    func = re.sub(r"^0x[0-9a-fA-F]+\s+(?:in\s+)?", "", func)
    func = re.sub(r"<[^<>]*>", "", func)
    func = func.split("(")[0].strip()
    return func if func else "unknown"


def _parse_backtrace_to_canonical(
    backtrace: List[str], raw_storage: Optional[List[str]] = None
) -> List[CallNode]:
    """
    GDB backtrace → Canonical CallNode list (execution order)

    转换流程：
    1. 解析每个 frame → (gdb_index, func, ...)
    2. 翻转列表（GDB #n → #0 变为 execution root → crash）
    3. 分配 exec_depth（0=root, max=crash）
    4. 去除连续重复帧（递归噪声）

    Args:
        backtrace: GDB backtrace 行列表（#0=crash）
        raw_storage: 可选，存储原始 frame 字符串的列表

    Returns:
        按 execution order 排列的 CallNode 列表
    """
    # Step 1: 解析所有 frame
    parsed_frames = []
    for line in backtrace:
        result = _parse_frame(line)
        if result:
            gdb_idx, func, src, addr = result
            parsed_frames.append((gdb_idx, func, src, addr, line))

    if not parsed_frames:
        return []

    # Step 2: 翻转为 execution order（#n → #0 变为 root → crash）
    parsed_frames.reverse()

    # Step 3: 分配 exec_depth 并构建 CallNode
    nodes = []
    for exec_depth, (gdb_idx, func, src, addr, raw) in enumerate(parsed_frames):
        nodes.append(
            CallNode(
                name=func,
                gdb_depth=gdb_idx,
                exec_depth=exec_depth,
                raw=raw,
                source=src,
                address=addr,
            )
        )
        if raw_storage is not None:
            raw_storage.append(raw)

    # Step 4: 去除连续重复帧（递归展开噪声）
    return _dedup_consecutive_frames(nodes)


def _dedup_consecutive_frames(nodes: List[CallNode]) -> List[CallNode]:
    """
    去除连续重复调用（保持 execution order）

    Example:
        [A, B, B, B, C] → [A, B, C]
    """
    if not nodes:
        return []

    result = [nodes[0]]
    for node in nodes[1:]:
        if node.name != result[-1].name:
            result.append(node)
    return result


def _build_edges(callstack: List[CallNode]) -> List[CallEdge]:
    """
    从 canonical callstack 构建调用边

    Args:
        callstack: 按 execution order 排列（root → crash）

    Returns:
        调用边列表（caller → callee）
    """
    edges = []
    for i in range(len(callstack) - 1):
        caller = callstack[i].name  # 执行序靠前
        callee = callstack[i + 1].name  # 执行序靠后
        edges.append(CallEdge(caller=caller, callee=callee))
    return edges


def _detect_cycles(edges: List[CallEdge]) -> List[Tuple[str, str]]:
    """检测调用环（双向边）"""
    seen_pairs: Set[Tuple[str, str]] = set()
    cycles = []
    for e in edges:
        pair = (e.caller, e.callee)
        reverse = (e.callee, e.caller)
        if reverse in seen_pairs:
            cycles.append(pair)
        seen_pairs.add(pair)
    return cycles


def _build_crash_signature(callstack: List[CallNode], depth: int = 4) -> str:
    """
    生成 crash 特征串（用于聚合相同类型崩溃）

    策略：从 crash 点向 root 方向回溯 N 层

    Args:
        callstack: canonical order（root → crash）
        depth: 回溯深度（包含 crash 点）

    Returns:
        特征串，格式：crash_func < caller1 < caller2 < ...

    Example:
        callstack = [main, foo, bar, crash]
        depth = 3
        → "crash < bar < foo"
    """
    if not callstack:
        return "unknown"

    crash_to_root = [
        n
        for n in reversed(callstack)
        if not any(skip in n.name for skip in ("__libc", "pthread_", "_start"))
    ]
    key_frames = crash_to_root[:depth]
    return " < ".join(node.name for node in key_frames)


def _find_common_frames(thread_chains: Dict[str, ThreadChain]) -> List[str]:
    """找出所有线程共同出现的函数帧（交集）"""
    if not thread_chains:
        return []

    frame_sets = [
        {node.name for node in chain.callstack} - _INVALID_FUNCS
        for chain in thread_chains.values()
    ]

    common = frame_sets[0].intersection(*frame_sets[1:])
    common -= _INVALID_FUNCS
    return sorted(common)


def _safe(x):
    if isinstance(x, list):
        return x[0] if x else "unknown"
    return x


def _build_global_call_graph(
    main,
    threads,
):
    graph: Dict[str, Set[str]] = defaultdict(set)

    for edge in main.edges:
        caller = _safe(edge.caller)
        callee = _safe(edge.callee)
        graph[caller].add(callee)

    for chain in threads.values():
        for edge in chain.edges:
            caller = _safe(edge.caller)
            callee = _safe(edge.callee)
            graph[caller].add(callee)

    return dict(graph)


def to_llm_input(
    result: CallChainResult, raw_meta: dict = None, context: dict = None
) -> dict:

    raw_meta = raw_meta or {}
    callstack = result.main_thread.callstack
    is_truncated = (
        raw_meta.get("suggest_rerun_with_debuginfo", False)
        or (
            len(callstack) <= 1
            and not any(n.source for n in callstack)  # 无任何源文件位置
        )
    )

    # ── 截断降级路径 ──
    if is_truncated:
        return {
            "analysis_mode": "env_diagnostic",
            "backtrace_quality": "insufficient",
            "backtrace_warning": (
                "backtrace 仅有 1 帧且无调试符号，调用链不可用。"
                "禁止基于调用链推断根因。"
            ),
            "crash_function": result.crash_function,
            "signal": raw_meta.get("signal_name", "未知"),
            "crash_address_region": raw_meta.get("crash_address_region", "未知"),
            "thread_count": (raw_meta.get("threads") or {}).get("total", 1),
            "crashed_thread": str((raw_meta.get("threads") or {}).get("crashed", {})),
            "abnormal_threads": (raw_meta.get("threads") or {}).get("abnormal", []),
            "rerun_suggestion": "使用 -g 重新编译并保留调试符号后复现",
            # 以下字段置空，防止 prompt 模板访问时 KeyError
            "crash_context_frames": "",
            "execution_path": "",
            "execution_path_note": "",
            "threads_detail": "",
            "common_frames_note": "",
            "call_graph_hotspots": "",
            "parse_warnings": "",
            "crash_signature": result.crash_signature,
            "main_path": "",
        }

    main = result.main_thread
    callstack = main.callstack

    # ── 1. 崩溃现场（最关键的 N 帧，带源码位置）──
    crash_context = []
    for node in reversed(callstack[-8:]):  # crash 端取 8 帧
        loc = f" @ {node.source}" if node.source else ""
        crash_context.append(f"  #{node.gdb_depth:>2} {node.name}{loc}")

    # ── 2. 调用路径摘要（分段，突出入口和崩溃点）──
    if len(callstack) > 12:
        head = [n.name for n in callstack[:3]]
        tail = [n.name for n in callstack[-5:]]
        path_summary = " → ".join(head) + "  …  " + " → ".join(tail)
        omitted = len(callstack) - 8
        path_note = f"(full depth: {len(callstack)}, {omitted} frames omitted)"
    else:
        path_summary = " → ".join(n.name for n in callstack)
        path_note = ""

    # ── 3. 线程异常信号（找出与主线程崩溃函数相同的线程）──
    suspicious_threads = []
    for tid, chain in result.threads.items():
        thread_funcs = {n.name for n in chain.callstack}
        overlap = thread_funcs & {n.name for n in callstack[-5:]}
        tail_repr = " → ".join(n.name for n in chain.callstack[-4:])
        if overlap:
            suspicious_threads.append(
                f"  [{tid}] shares frames {overlap} | tail: {tail_repr}"
            )
        else:
            suspicious_threads.append(f"  [{tid}] {tail_repr}")

    # ── 4. 公共帧（暗示系统级共享状态）──
    common_note = (
        "Threads share frames: " + ", ".join(result.common_frames)
        if result.common_frames
        else "No common frames across threads"
    )

    # ── 5. 解析警告（符号可信度）──
    warnings_text = ""
    if result.parse_warnings:
        warnings_text = "⚠ Parse warnings:\n" + "\n".join(
            f"  - {w['type']}: declared={w.get('declared')} resolved={w.get('resolved')}"
            for w in result.parse_warnings
        )

    # ── 6. 调用图中的高扇出节点（潜在共享资源竞争点）──
    hotspots = [
        f"  {caller} → [{len(callees)} callees]: {', '.join(sorted(callees)[:4])}"
        for caller, callees in result.call_graph.items()
        if len(callees) >= 3
    ]

    return {
        "main_path": " → ".join(n.name for n in result.main_thread.callstack),
        # 给 LLM 的顶层诊断提示
        "crash_function": result.crash_function,
        "crash_signature": result.crash_signature,
        # 崩溃现场（最重要）
        "crash_context_frames": "\n".join(crash_context),
        # 完整路径摘要（结构感）
        "execution_path": path_summary,
        "execution_path_note": path_note,
        # 线程视角
        "thread_count": len(result.threads) + 1,
        "threads_detail": (
            "\n".join(suspicious_threads) if suspicious_threads else "single-threaded"
        ),
        "common_frames_note": common_note,
        # 潜在问题点
        "call_graph_hotspots": "\n".join(hotspots) if hotspots else "none",
        # 可信度
        "parse_warnings": warnings_text,
    }


def parse_call_chain(
    backtrace: List[str],
    threads_bt: Optional[Dict[str, List[str]]] = None,
    crash_frame: Optional[Dict[str, Any]] = None,
) -> CallChainResult:
    """
    解析调用链（主入口）

    所有返回数据遵循 CANONICAL REPRESENTATION（execution order）

    Args:
        backtrace:   主线程 GDB backtrace（#0=crash, #n=root）
        threads_bt:  {tid: backtrace_lines}
        crash_frame: crash 帧元数据（可选）

    Returns:
        CallChainResult（所有数据按 execution order 组织）
    """

    def unwrap_backtrace(bt):
        if isinstance(bt, tuple):
            bt = bt[0]
        return bt

    backtrace = unwrap_backtrace(backtrace)
    main_callstack = _parse_backtrace_to_canonical(backtrace)

    if not main_callstack:
        # 空 backtrace 的降级处理
        return CallChainResult(
            crash_function="unknown",
            crash_signature="unknown",
            main_thread=ThreadChain(tid="main"),_FRAME_PATTERNS = [
    # 模式1：带地址 + 带参数 + 带源文件
    # #0  0x0000564a6fba39f7 in main (argc=6, argv=0x...) at file.c:44
    re.compile(
        r"^#(?P<idx>\d+)\s+"
        r"(?P<addr>0x[0-9a-fA-F]+)?\s*"
        r"(?:in\s+)?"
        r"(?P<func>[^\s(]+)"
        r"(?:\s*\([^)]*(?:\([^)]*\)[^)]*)*\))?"  # 修改：支持嵌套括号参数
        r"(?:\s+at\s+(?P<src>\S+:\d+))?"
    ),
    # 模式2：无地址 + from 共享库
    re.compile(
        r"^#(?P<idx>\d+)\s+"
        r"(?P<func>[^\s(]+)"
        r"(?:\s*\([^)]*\))?"
        r"(?:\s+from\s+(?P<src>\S+))?"
    ),
]
        )

    main_chain = ThreadChain(
        tid="main",
        callstack=main_callstack,
        edges=_build_edges(main_callstack),
        crash_func=main_callstack[-1].name,  # execution order 最后一个
    )

    declared_crash = (
        _normalize_func(crash_frame.get("function", "")) if crash_frame else None
    )

    resolved_crash = main_chain.crash_func
    mismatches = []

    if declared_crash and declared_crash != resolved_crash:
        mismatches = []
        if declared_crash and declared_crash != resolved_crash:
            mismatches.append(
                {
                    "type": "crash_frame_mismatch",
                    "declared": declared_crash,  # crash_frame 字段说的是这个函数
                    "resolved": resolved_crash,  # backtrace #0 实际解析出来的是这个
                }
            )

    thread_chains: Dict[str, ThreadChain] = {}
    if threads_bt:
        for tid, bt in threads_bt.items():
            callstack = _parse_backtrace_to_canonical(bt)
            if callstack:
                thread_chains[tid] = ThreadChain(
                    tid=tid,
                    callstack=callstack,
                    edges=_build_edges(callstack),
                    crash_func=callstack[-1].name,
                )

    all_chains = {"main": main_chain, **thread_chains}
    common_frames = _find_common_frames(all_chains)
    call_graph = _build_global_call_graph(main_chain, thread_chains)

    cycles = _detect_cycles(main_chain.edges)
    if cycles:
        import warnings

        warnings.warn(f"检测到调用环（可能为递归或符号错误）: {cycles}", stacklevel=2)

    signature = _build_crash_signature(main_callstack, depth=20)

    return CallChainResult(
        crash_function=resolved_crash,
        crash_signature=signature,
        main_thread=main_chain,
        threads=thread_chains,
        common_frames=common_frames,
        call_graph=call_graph,
        parse_warnings=mismatches,
    )
