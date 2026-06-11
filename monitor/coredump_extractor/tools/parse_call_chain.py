import re
import warnings as _warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Optional, Set, Tuple, Any


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
    gdb_depth: int
    exec_depth: int
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

    caller: str
    callee: str
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
    crash_signature: str
    main_thread: ThreadChain
    threads: Dict[str, ThreadChain] = field(default_factory=dict)
    common_frames: List[str] = field(default_factory=list)
    call_graph: Dict[str, Set[str]] = field(default_factory=dict)
    parse_warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "crash_function": self.crash_function,
            "crash_signature": self.crash_signature,
            "main_thread": self.main_thread.to_dict(),
            "threads": {k: v.to_dict() for k, v in self.threads.items()},
            "common_frames": self.common_frames,
            "call_graph": {k: list(v) for k, v in self.call_graph.items()},
        }


# ── DPDK Frame Classifier ──────────────────────────────────────────────────

_PMD_PREFIXES: tuple[str, ...] = (
    "i40e_", "mlx5_", "ixgbe_", "ena_", "ice_", "nfp_", "hns3_",
    "virtio_", "vmxnet3_", "bnxt_", "axgbe_", "enic_", "fm10k_",
    "e1000_", "igb_", "igbvf_", "cnxk_", "octeontx_", "af_xdp_",
    "dpaa_", "dpaa2_", "mvpp2_", "mvneta_",
)

_EAL_PREFIXES: tuple[str, ...] = ("rte_eal_", "eal_", "rte_mp_", "eal_thread")

_EAL_EXACT: frozenset[str] = frozenset({
    "rte_panic", "rte_exit", "__rte_panic", "mp_handle",
    "eal_intr_handle_events", "rte_ctrl_thread_create",
})

_NOISE_EXACT: frozenset[str] = frozenset({"??", "unknown", "_start", "__libc_start_main"})

_LIBC_PREFIXES: tuple[str, ...] = ("__libc_", "__glibc_", "pthread_", "__pthread", "clone3")

_LAYER_RULES: list[tuple[str, Callable[[str], bool]]] = [
    ("noise",    lambda f: f in _NOISE_EXACT or f == ""),
    ("libc",     lambda f: any(f.startswith(p) for p in _LIBC_PREFIXES)),
    ("dpdk_pmd", lambda f: any(f.startswith(p) for p in _PMD_PREFIXES)),
    ("dpdk_eal", lambda f: any(f.startswith(p) for p in _EAL_PREFIXES) or f in _EAL_EXACT),
    ("dpdk_lib", lambda f: f.startswith("rte_")),
    ("user_app", lambda f: True),
]


class DPDKFrameClassifier:
    """将函数名映射到语义层（noise/libc/dpdk_pmd/dpdk_eal/dpdk_lib/user_app）。"""

    def classify(self, func_name: str) -> str:
        for layer, predicate in _LAYER_RULES:
            if predicate(func_name):
                return layer
        return "user_app"


# ── DPDK Crash Pattern Matcher ─────────────────────────────────────────────

@dataclass(frozen=True)
class CrashPattern:
    key: str
    description: str


_PatternRule = tuple[CrashPattern, Callable[[Set[str], str, str, str, Optional[str]], bool]]

_BUILT_IN_PATTERNS: list[_PatternRule] = [
    (
        CrashPattern(
            "mempool_exhaustion",
            "调用链显示 mempool/mbuf 分配失败路径，疑似 mempool 耗尽导致崩溃。"
            "根因应优先排查 mempool 配置和 mbuf 回收逻辑。",
        ),
        lambda ns, sig, layer, region, fa: bool(
            ns & {"rte_mempool_get", "rte_pktmbuf_alloc", "rte_mempool_generic_get",
                  "rte_mempool_get_bulk", "rte_pktmbuf_alloc_bulk"}
        ),
    ),
    (
        CrashPattern(
            "mempool_exhaustion_null_deref",
            "出错地址为 NULL 或 NULL 结构体偏移（near-null），且程序链接了 DPDK mbuf 库。"
            "高度疑似 rte_pktmbuf_alloc() 返回 NULL 后被解引用（内联宏导致帧不可见）。"
            "根因：mempool 耗尽。应检查 mempool 配置大小与 mbuf 回收路径。",
        ),
        lambda ns, sig, layer, region, fa: (
            sig in ("SIGSEGV", "11")
            and fa is not None
            and _is_near_null(fa)
        ),
    ),
    (
        CrashPattern(
            "ring_assert_failure",
            "调用链经过 ring 入/出队操作，配合 SIGABRT 信号，疑似 ring 断言失败"
            "（队列满/空边界违规）。",
        ),
        lambda ns, sig, layer, region, fa: (
            bool(ns & {"rte_ring_enqueue", "rte_ring_dequeue",
                       "rte_ring_enqueue_bulk", "rte_ring_dequeue_bulk"})
            and sig in ("SIGABRT", "6")
        ),
    ),
    (
        CrashPattern(
            "pmd_driver_crash",
            "崩溃帧位于 PMD 驱动层，根因在网卡驱动内部。"
            "应检查驱动版本、固件版本及设备绑定状态。",
        ),
        lambda ns, sig, layer, region, fa: layer == "dpdk_pmd",
    ),
    (
        CrashPattern(
            "null_ptr_in_anonymous_region",
            "崩溃地址区域为匿名映射（anonymous），结合 SIGSEGV 信号，"
            "高度疑似空指针/野指针解引用。",
        ),
        lambda ns, sig, layer, region, fa: (
            sig in ("SIGSEGV", "11") and region in ("anonymous", "未知", "", None)
        ),
    ),
    (
        CrashPattern(
            "eal_panic_abort",
            "调用链经过 rte_panic/rte_exit，DPDK 主动触发了 abort。"
            "检查前置的错误日志确认 panic 原因。",
        ),
        lambda ns, sig, layer, region, fa: (
            bool(ns & {"rte_panic", "rte_exit", "__rte_panic"})
            and sig in ("SIGABRT", "6")
        ),
    ),
]


def _is_near_null(faulting_address: str) -> bool:
    try:
        return int(faulting_address, 16) < 0x1000
    except (ValueError, TypeError):
        return False


class DPDKCrashPatternMatcher:
    """根据调用链特征匹配 DPDK 已知崩溃模式。"""

    def __init__(self, patterns: list[_PatternRule] | None = None) -> None:
        self._patterns = patterns if patterns is not None else _BUILT_IN_PATTERNS

    def match(
        self,
        callstack_names: Set[str],
        signal_name: str,
        crash_layer: str,
        crash_address_region: str,
        faulting_address: Optional[str] = None,
    ) -> CrashPattern | None:
        for pattern, predicate in self._patterns:
            if predicate(callstack_names, signal_name, crash_layer, crash_address_region, faulting_address):
                return pattern
        return None


# ── Layered path builder ───────────────────────────────────────────────────

def _build_layered_path(callstack: List[CallNode], classifier: DPDKFrameClassifier) -> str:
    """
    将调用栈按语义层分组后输出，同层内超过 3 帧则折叠中间帧，
    保留跨层边界的完整信息。
    """
    groups: list[tuple[str, list[str]]] = []
    for node in callstack:
        layer = classifier.classify(node.name)
        if layer == "noise":
            continue
        if groups and groups[-1][0] == layer:
            groups[-1][1].append(node.name)
        else:
            groups.append((layer, [node.name]))

    lines: list[str] = []
    for layer, names in groups:
        if len(names) > 3:
            display = names[:2] + ["…"] + [names[-1]]
        else:
            display = list(names)
        lines.append(f"  [{layer}] {' → '.join(display)}")
    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────────

_FRAME_PATTERNS = [
    re.compile(
        r"^#(?P<idx>\d+)\s+"
        r"(?P<addr>0x[0-9a-fA-F]+)?\s*"
        r"(?:in\s+)?"
        r"(?P<func>[^\s(]+)"
        r"(?:\s*\(.*?\))?"
        r"(?:\s+at\s+(?P<src>\S+:\d+))?",
        re.DOTALL,
    ),
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
    line = raw.strip()
    if not line.startswith("#"):
        return None

    for pattern in _FRAME_PATTERNS:
        m = pattern.match(line)
        if not m:
            continue

        groups = m.groupdict()
        func = _normalize_func(groups.get("func") or "")
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
    func = raw_func.strip()
    func = re.sub(r"^0x[0-9a-fA-F]+\s+(?:in\s+)?", "", func)
    func = re.sub(r"<[^<>]*>", "", func)
    func = func.split("(")[0].strip()
    return func if func else "unknown"


def _parse_backtrace_to_canonical(
    backtrace: List[str], raw_storage: Optional[List[str]] = None
) -> List[CallNode]:
    parsed_frames = []
    for line in backtrace:
        result = _parse_frame(line)
        if result:
            gdb_idx, func, src, addr = result
            parsed_frames.append((gdb_idx, func, src, addr, line))

    if not parsed_frames:
        return []

    parsed_frames.reverse()

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

    return _dedup_consecutive_frames(nodes)


def _dedup_consecutive_frames(nodes: List[CallNode]) -> List[CallNode]:
    if not nodes:
        return []
    result = [nodes[0]]
    for node in nodes[1:]:
        if node.name != result[-1].name:
            result.append(node)
    return result


def _build_edges(callstack: List[CallNode]) -> List[CallEdge]:
    edges = []
    for i in range(len(callstack) - 1):
        edges.append(CallEdge(caller=callstack[i].name, callee=callstack[i + 1].name))
    return edges


def _callstacks_equal(a: List[CallNode], b: List[CallNode]) -> bool:
    """判断两个解析后的调用栈是否代表同一条执行路径（仅比较函数名序列）。"""
    if len(a) != len(b):
        return False
    return all(x.name == y.name for x, y in zip(a, b))


def _detect_cycles(edges: List[CallEdge]) -> List[Tuple[str, str]]:
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


def _build_global_call_graph(main: ThreadChain, threads: Dict[str, ThreadChain]) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = defaultdict(set)
    for edge in main.edges:
        graph[_safe(edge.caller)].add(_safe(edge.callee))
    for chain in threads.values():
        for edge in chain.edges:
            graph[_safe(edge.caller)].add(_safe(edge.callee))
    return dict(graph)


# ── Call Chain Parser ──────────────────────────────────────────────────────

class CallChainParser:
    """
    调用链解析器：将 GDB backtrace 构建为图结构，并序列化为 LLM 输入。
    """

    def __init__(
        self,
        classifier: DPDKFrameClassifier | None = None,
        pattern_matcher: DPDKCrashPatternMatcher | None = None,
    ) -> None:
        self._classifier = classifier or DPDKFrameClassifier()
        self._matcher = pattern_matcher or DPDKCrashPatternMatcher()

    def parse(
        self,
        backtrace: List[str],
        threads_bt: Optional[Dict[str, List[str]]] = None,
        crash_frame: Optional[Dict[str, Any]] = None,
    ) -> CallChainResult:
        if isinstance(backtrace, tuple):
            backtrace = backtrace[0]

        main_callstack = _parse_backtrace_to_canonical(backtrace)

        if not main_callstack:
            return CallChainResult(
                crash_function="unknown",
                crash_signature="unknown",
                main_thread=ThreadChain(tid="main"),
            )

        main_chain = ThreadChain(
            tid="main",
            callstack=main_callstack,
            edges=_build_edges(main_callstack),
            crash_func=main_callstack[-1].name,
        )

        declared_crash = (
            _normalize_func(crash_frame.get("function", "")) if crash_frame else None
        )
        resolved_crash = main_chain.crash_func
        mismatches = []
        if declared_crash and declared_crash != resolved_crash:
            mismatches.append(
                {
                    "type": "crash_frame_mismatch",
                    "declared": declared_crash,
                    "resolved": resolved_crash,
                }
            )

        thread_chains: Dict[str, ThreadChain] = {}
        if threads_bt:
            for tid, bt in threads_bt.items():
                callstack = _parse_backtrace_to_canonical(bt)
                if callstack and not _callstacks_equal(callstack, main_callstack):
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
            _warnings.warn(f"检测到调用环（可能为递归或符号错误）: {cycles}", stacklevel=2)

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

    def to_llm_input(
        self,
        result: CallChainResult,
        raw_meta: dict = None,
        context: dict = None,
    ) -> dict:
        raw_meta = raw_meta or {}
        callstack = result.main_thread.callstack
        is_truncated = (
            raw_meta.get("suggest_rerun_with_debuginfo", False)
            or (
                len(callstack) <= 1
                and not any(n.source for n in callstack)
            )
        )

        if is_truncated:
            # Even in env_diagnostic mode, attempt pattern matching with si_addr
            faulting_address = raw_meta.get("faulting_address")
            signal_name = raw_meta.get("signal_name", "")
            crash_layer = self._classifier.classify(result.crash_function)
            crash_address_region = raw_meta.get("crash_address_region", "")
            matched_pattern = self._matcher.match(
                set(), signal_name, crash_layer, crash_address_region, faulting_address
            )
            crash_pattern_text = matched_pattern.description if matched_pattern else ""

            return {
                "analysis_mode": "env_diagnostic",
                "backtrace_quality": "insufficient",
                "backtrace_warning": (
                    "backtrace 仅有 1 帧且无调试符号，调用链不可用。"
                    "禁止基于调用链推断根因。"
                ),
                "crash_function": result.crash_function,
                "crash_layer": crash_layer,
                "crash_pattern": crash_pattern_text,
                "faulting_address": faulting_address,
                "signal": signal_name,
                "crash_address_region": crash_address_region,
                "thread_count": (raw_meta.get("threads") or {}).get("total", 1),
                "crashed_thread": str((raw_meta.get("threads") or {}).get("crashed", {})),
                "abnormal_threads": (raw_meta.get("threads") or {}).get("abnormal", []),
                "rerun_suggestion": "使用 -g 重新编译并保留调试符号后复现",
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

        # Semantic layer of crash frame
        crash_layer = self._classifier.classify(result.crash_function)

        # Pattern matching
        callstack_names: Set[str] = {n.name for n in callstack}
        signal_name = raw_meta.get("signal_name", "")
        crash_address_region = raw_meta.get("crash_address_region", "")
        faulting_address = raw_meta.get("faulting_address")
        matched_pattern = self._matcher.match(
            callstack_names, signal_name, crash_layer, crash_address_region, faulting_address
        )
        crash_pattern_text = matched_pattern.description if matched_pattern else ""

        # Layered execution path (replaces hard truncation)
        layered_path = _build_layered_path(callstack, self._classifier)

        # Crash context: last 8 frames with layer annotation
        crash_context = []
        for node in reversed(callstack[-8:]):
            layer = self._classifier.classify(node.name)
            loc = f" @ {node.source}" if node.source else ""
            crash_context.append(f"  #{node.gdb_depth:>2} [{layer}] {node.name}{loc}")

        # Compact execution path for single-line summary
        if len(callstack) > 12:
            head = [n.name for n in callstack[:3]]
            tail = [n.name for n in callstack[-5:]]
            path_summary = " → ".join(head) + "  …  " + " → ".join(tail)
            omitted = len(callstack) - 8
            path_note = f"(full depth: {len(callstack)}, {omitted} frames omitted)"
        else:
            path_summary = " → ".join(n.name for n in callstack)
            path_note = ""

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

        common_note = (
            "Threads share frames: " + ", ".join(result.common_frames)
            if result.common_frames
            else "No common frames across threads"
        )

        warnings_text = ""
        if result.parse_warnings:
            warnings_text = "⚠ Parse warnings:\n" + "\n".join(
                f"  - {w['type']}: declared={w.get('declared')} resolved={w.get('resolved')}"
                for w in result.parse_warnings
            )

        hotspots = [
            f"  {caller} → [{len(callees)} callees]: {', '.join(sorted(callees)[:4])}"
            for caller, callees in result.call_graph.items()
            if len(callees) >= 3
        ]

        return {
            "analysis_mode": "call_chain_diagnostic",
            "signal": signal_name,
            "main_path": " → ".join(n.name for n in result.main_thread.callstack),
            "crash_function": result.crash_function,
            "crash_layer": crash_layer,
            "crash_pattern": crash_pattern_text,
            "crash_signature": result.crash_signature,
            "faulting_address": faulting_address,
            "crash_context_frames": "\n".join(crash_context),
            "execution_path": path_summary,
            "execution_path_note": path_note,
            "layered_execution_path": layered_path,
            "thread_count": len(result.threads) + 1,
            "threads_detail": (
                "\n".join(suspicious_threads) if suspicious_threads else "single-threaded"
            ),
            "common_frames_note": common_note,
            "call_graph_hotspots": "\n".join(hotspots) if hotspots else "none",
            "parse_warnings": warnings_text,
        }


# 模块级兼容函数，供旧代码直接调用
_default_parser = CallChainParser()


def parse_call_chain(
    backtrace: List[str],
    threads_bt: Optional[Dict[str, List[str]]] = None,
    crash_frame: Optional[Dict[str, Any]] = None,
) -> CallChainResult:
    return _default_parser.parse(backtrace, threads_bt, crash_frame)


def to_llm_input(
    result: CallChainResult, raw_meta: dict = None, context: dict = None
) -> dict:
    return _default_parser.to_llm_input(result, raw_meta, context)
