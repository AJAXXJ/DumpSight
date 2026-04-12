import os
import re
from typing import Optional, TypedDict, Union
from monitor.coredump_extractor.tools.parse_call_chain import parse_call_chain, to_llm_input
from tools.constant import IDLE_FRAMES, SUBSYSTEMS, KEY_REGISTER


class SignalInfo(TypedDict):
    name: str
    description: str


class CrashFrame(TypedDict):
    function: str
    file: Optional[str]
    line: Optional[str]
    has_debuginfo: bool


class ThreadInfo(TypedDict):
    id: str
    lwp: str
    bt_top: str


class ThreadSummary(TypedDict):
    total: int
    crashed: Optional[ThreadInfo]
    abnormal: list[ThreadInfo]
    idle: int


class AddressRegion(TypedDict):
    region: str
    start: str
    end: str
    type: str


class SharedLib(TypedDict):
    path: str
    basename: str
    loaded: bool
    text_start: str
    text_end: str


class GdbParseResult(TypedDict):
    signal: Optional[SignalInfo]
    crash_type: str
    crash_frame: Optional[CrashFrame]
    backtrace: list[str]
    registers: dict[str, str]
    stack_memory: dict[str, list[str]]
    threads: ThreadSummary
    threads_bt: dict[str, list[str]]
    shared_libs: list[SharedLib]
    dpdk_subsystems: list[str]
    crash_address_type: Optional[AddressRegion]
    warnings: list[str]


_RE_SIGNAL = re.compile(
    r"Program (?:received|terminated with) signal (\w+|SIG\w+|\d+)[,.]?\s*(.*)?"
)
_RE_CRASH_FRAME = re.compile(
    r"#0\s+(?:0x[0-9a-f]+\s+in\s+)?(.+?)(?:\s+at\s+(.+):(\d+))?$",
    re.MULTILINE,
)
_RE_FRAME_LINE = re.compile(r"^\s*#(\d+)\s+(.*)$")
_RE_THREAD_INFO = re.compile(
    r"^\s*(\*?)\s*(\d+)\s+Thread\s+(0x[0-9a-f]+)\s+\(LWP\s+(\d+)\)\s+(.+?)$",
    re.MULTILINE,
)
_RE_THREAD_HEAD = re.compile(
    r"^\s*Thread\s+(\d+)\s+\(Thread\s+0x[0-9a-f]+\s+\(LWP\s+(\d+)\)\):?\s*$"
)
_RE_REGISTER_KV = re.compile(r"(\w+)\s+(0x[0-9a-f]+)")
_RE_MAPPING = re.compile(
    r"(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+0x[0-9a-f]+\s*(.*?)$",
    re.MULTILINE,
)
_RE_SHARED_LIB = re.compile(
    r"(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(Yes|No)\s+(.+\.so\S*)"
)
_RE_HEX = re.compile(r"0x[0-9a-f]+")

# section 分隔符模板（动态构造，避免重复 re.escape）
_SECTION_RE_CACHE: dict[str, re.Pattern] = {}


def _get_section_re(begin: str, end: str) -> re.Pattern:
    key = (begin, end)
    if key not in _SECTION_RE_CACHE:
        _SECTION_RE_CACHE[key] = re.compile(
            rf"{re.escape(begin)}\s*(.*?)\s*{re.escape(end)}",
            re.DOTALL,
        )
    return _SECTION_RE_CACHE[key]


def _norm_text(s: str) -> str:
    return re.sub(r"[\s_()]+", "", (s or "").lower())


# 将 IDLE_FRAMES 常量与内置关键字合并为归一化 token 集合
_IDLE_TOKENS: frozenset[str] = frozenset(filter(None, (
    _norm_text(x) for x in IDLE_FRAMES
))) | frozenset({
    "read", "libcread", "epollwait", "pthreadcondwait",
    "pthreadcondtimedwait", "futexwait", "nanosleep", "clocknanosleep",
})

# KEY_REGISTER 集合化，O(1) 查询
_KEY_REGISTER_SET: frozenset[str] = frozenset(KEY_REGISTER)

# SUBSYSTEMS 预编译
_SUBSYSTEM_RES: dict[str, re.Pattern] = {
    name: re.compile(pattern) for name, pattern in SUBSYSTEMS.items()
}


def _is_idle_frame_text(text: str) -> bool:
    """判断某帧是否处于等待/idle 状态。"""
    t = _norm_text(text)
    if not t:
        return False
    return any(tok in t for tok in _IDLE_TOKENS)


def _classify_sigsegv(registers: dict[str, str]) -> str:
    if registers.get("rdi") == "0x0":
        return "null_pointer_deref"
    if registers.get("rip") == "0x0":
        return "null_function_call"
    return "invalid_memory_access"


_SIGNAL_CLASSIFIERS: dict[str, object] = {
    "SIGSEGV": _classify_sigsegv,
    "SIGBUS":  lambda _: "bus_error_alignment",
    "SIGABRT": lambda _: "abort",
    "SIGFPE":  lambda _: "floating_point_exception",
    "SIGILL":  lambda _: "illegal_instruction",
    "SIGPIPE": lambda _: "broken_pipe",
}


def classify_crash(signal_info: Optional[SignalInfo], registers: dict[str, str]) -> str:
    """根据信号和寄存器初步分类崩溃原因。"""
    if not signal_info:
        return "unknown"
    sig = signal_info.get("name", "")
    handler = _SIGNAL_CLASSIFIERS.get(sig)
    if handler:
        return handler(registers)
    return sig or "unknown"


def get_section(output: str, begin: str, end: str) -> str:
    """从完整 GDB 输出中提取 begin/end 之间的区块，缺失返回空字符串。"""
    m = _get_section_re(begin, end).search(output)
    return m.group(1).strip() if m else ""


def _extract_all_sections(output: str) -> dict[str, str]:
    """预提取所有 section，避免重复正则搜索。"""
    pairs = [
        ("bt_full",     "=== BT_FULL_BEGIN ===",     "=== BT_FULL_END ==="),
        ("info_threads","=== INFO_THREADS_BEGIN ===", "=== INFO_THREADS_END ==="),
        ("registers",   "=== REGISTERS_BEGIN ===",   "=== REGISTERS_END ==="),
        ("mappings",    "=== MAPPINGS_BEGIN ===",     "=== MAPPINGS_END ==="),
        ("shared",      "=== SHARED_BEGIN ===",       "=== SHARED_END ==="),
        ("thread_bt",   "=== THREAD_BT_BEGIN ===",    "=== THREAD_BT_END ==="),
        ("rsp",         "=== RSP_BEGIN ===",           "=== RSP_END ==="),
        ("rbp",         "=== RBP_BEGIN ===",           "=== RBP_END ==="),
        ("args",        "=== ARGS_BEGIN ===",          "=== ARGS_END ==="),
    ]
    return {key: get_section(output, begin, end) for key, begin, end in pairs}


def extract_signal(output: str) -> Optional[SignalInfo]:
    """提取信号信息。"""
    m = _RE_SIGNAL.search(output)
    if m:
        return {
            "name":        m.group(1).strip(),
            "description": (m.group(2) or "").strip(),
        }
    return None


def extract_crash_frame(bt_full_section: str) -> Optional[CrashFrame]:
    """崩溃精确位置：函数名、文件、行号（仅解析 BT_FULL 区块）。"""
    if not bt_full_section:
        return None
    m = _RE_CRASH_FRAME.search(bt_full_section)
    if m:
        return {
            "function":      m.group(1).strip(),
            "file":          m.group(2),
            "line":          m.group(3),
            "has_debuginfo": m.group(2) is not None,
        }
    return None


def extract_backtrace(bt_full_section: str, max_frames: int = 30) -> list[str]:
    """调用栈：取前 N 帧（仅解析 BT_FULL 区块）。"""
    if not bt_full_section:
        return []
    frames: list[str] = []
    seen_no: set[int] = set()
    for line in bt_full_section.splitlines():
        m = _RE_FRAME_LINE.match(line)
        if not m:
            continue
        # 统一转 int，避免 "#0" / "#00" / "# 0" 被当作不同帧号
        no = int(m.group(1))
        if no in seen_no:
            continue
        seen_no.add(no)
        frames.append(f"#{no} {m.group(2).strip()}")
        if len(frames) >= max_frames:
            break
    return frames


def extract_threads(info_threads_section: str) -> ThreadSummary:
    """所有线程状态：标记崩溃线程（仅解析 INFO_THREADS 区块）。"""
    if not info_threads_section:
        return {"total": 0, "crashed": None, "abnormal": [], "idle": 0}

    crashed_thread: Optional[ThreadInfo] = None
    abnormal_threads: list[ThreadInfo] = []
    total = 0

    for m in _RE_THREAD_INFO.finditer(info_threads_section):
        total += 1
        is_crashed = m.group(1).strip() == "*"
        top = m.group(5).strip()
        thread: ThreadInfo = {"id": m.group(2), "lwp": m.group(4), "bt_top": top}

        if is_crashed:
            crashed_thread = thread
        elif not _is_idle_frame_text(top):
            abnormal_threads.append(thread)

    idle = total - len(abnormal_threads) - (1 if crashed_thread else 0)
    return {
        "total":    total,
        "crashed":  crashed_thread,
        "abnormal": abnormal_threads,
        "idle":     max(idle, 0),   # 防止负数
    }


def extract_registers(registers_section: str) -> dict[str, str]:
    """
    关键寄存器：rip / rsp / rbp 和函数参数寄存器。
    单次扫描 section，再按 KEY_REGISTER 过滤，减少多次遍历。
    """
    if not registers_section:
        return {}
    return {
        k: v
        for k, v in _RE_REGISTER_KV.findall(registers_section)
        if k in _KEY_REGISTER_SET
    }


def extract_crash_address_type(
    registers: dict[str, str],
    mappings_section: str,
) -> Optional[AddressRegion]:
    """
    判断 rip/崩溃地址落在哪个内存区域（仅解析 MAPPINGS 区块）。
    同时与 shared_libs 交叉验证（通过 region 名称）。
    """
    rip = registers.get("rip")
    if not rip or not mappings_section:
        return None
    try:
        addr = int(rip, 16)
    except ValueError:
        return None

    for m in _RE_MAPPING.finditer(mappings_section):
        try:
            start = int(m.group(1), 16)
            end   = int(m.group(2), 16)
        except ValueError:
            continue
        name = m.group(3).strip()
        if start <= addr < end:
            return {
                "region": name or "anonymous",
                "start":  m.group(1),
                "end":    m.group(2),
                "type":   _classify_region(name),
            }
    return None


def extract_all_threads_bt(thread_bt_section: str) -> dict[str, list[str]]:
    """
    thread apply all bt 5 的输出（仅解析 THREAD_BT 区块）。
    只保留非 idle 线程的完整栈；同线程内按 frame_no 去重。

    拆分为：_parse_thread_blocks（纯解析）→ _filter_idle_threads（过滤）。
    """
    if not thread_bt_section:
        return {}
    raw = _parse_thread_blocks(thread_bt_section)
    return _filter_idle_threads(raw)


def _parse_thread_blocks(section: str) -> dict[str, list[str]]:
    """将 thread_bt section 解析为 {tid: [frame_str, ...]} 的原始映射。"""
    threads: dict[str, list[str]] = {}
    current_tid: Optional[str] = None
    current_frames: list[str] = []
    current_seen: set[int] = set()

    for line in section.splitlines():
        head = _RE_THREAD_HEAD.match(line)
        if head:
            if current_tid is not None and current_frames:
                threads[current_tid] = current_frames
            current_tid = head.group(1)
            current_frames = []
            current_seen = set()
            continue

        fm = _RE_FRAME_LINE.match(line)
        if current_tid and fm:
            no = int(fm.group(1))
            if no in current_seen:
                continue
            current_seen.add(no)
            current_frames.append(f"#{no} {fm.group(2).strip()}")

    if current_tid is not None and current_frames:
        threads[current_tid] = current_frames

    return threads


def _filter_idle_threads(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """过滤掉 idle 线程，仅保留有实际活动的线程。"""
    return {
        tid: frames
        for tid, frames in raw.items()
        if frames and not _is_idle_frame_text(frames[0])
    }


def extract_stack_memory(
    rsp_section: str,
    rbp_section: str,
) -> dict[str, list[str]]:
    """x/4xg $rsp 和 x/4xg $rbp 的输出（解析 RSP/RBP 分段）。"""
    result: dict[str, list[str]] = {}
    for label, section in [("rsp", rsp_section), ("rbp", rbp_section)]:
        if section:
            values = _RE_HEX.findall(section)
            if values:
                result[label] = values[1:]  # 跳过行首地址
    return result


DPDK_LIB_KEYWORDS = [
    "librte_eal",
    "librte_mbuf",
    "librte_ethdev",
    "librte_net",
    "librte_ring",
    "librte_malloc",
]


def extract_dpdk_lib_status(shared_section: str):
    """
    只检测 DPDK 关键 shared lib 是否缺失
    """
    if not shared_section:
        return {
            "dpdk_lib_missing": True,
            "found_libs": [],
            "missing_libs": DPDK_LIB_KEYWORDS
        }

    found = set()

    for lib in DPDK_LIB_KEYWORDS:
        if lib in shared_section:
            found.add(lib)

    missing = [lib for lib in DPDK_LIB_KEYWORDS if lib not in found]

    return {
        "dpdk_lib_missing": len(missing) > 0,
        "found_libs": list(found),
        "missing_libs": missing
    }


def extract_dpdk_subsystem(bt_full_section: str) -> list[str]:
    """
    从 bt_full 区块识别崩溃涉及的 DPDK 子系统。
    只在已切割的 bt 区块上搜索，避免全文扫描。
    """
    if not bt_full_section:
        return []
    return [
        name
        for name, pattern_re in _SUBSYSTEM_RES.items()
        if pattern_re.search(bt_full_section)
    ]


def _classify_region(name: str) -> str:
    if not name:
        return "anonymous"
    if name.startswith("[stack"):
        return "stack"
    if name.startswith("[heap"):
        return "heap"
    if name.startswith("[anon_hugepage]") or "/dev/hugepages" in name:
        return "hugepage"
    if "/var/run/dpdk" in name:
        return "dpdk_shared_mem"
    if "librte_" in name or name.endswith(".so") or ".so." in name:
        return "shared_lib"
    return "executable"


def _collect_warnings(result: dict) -> list[str]:
    """收集解析过程中的异常情况，便于下游判断结果可信度。"""
    warnings: list[str] = []
    if not result.get("signal"):
        warnings.append("signal section missing or unparseable")
    if not result.get("registers"):
        warnings.append("registers section missing")
    bt = result.get("backtrace", [])
    if len(bt) == 0:
        warnings.append("backtrace is empty")
    elif len(bt) < 3:
        warnings.append(f"backtrace only has {len(bt)} frame(s), may be truncated")
    threads = result.get("threads", {})
    if threads.get("total", 0) == 0:
        warnings.append("no threads parsed from info_threads section")
    if not result.get("crash_frame"):
        warnings.append("crash frame (#0) not found in bt_full section")
    return warnings


def parse_gdb_output(output: str) -> GdbParseResult:
    """解析完整 GDB 输出，返回结构化崩溃信息。"""
    signal   = extract_signal(output)
    sections = _extract_all_sections(output)
    registers = extract_registers(sections["registers"])

    backtrace = extract_backtrace(sections["bt_full"], max_frames=10),
    thread_bt = extract_all_threads_bt(sections["thread_bt"])
    crash_frame = extract_crash_frame(sections["bt_full"])

    call_chain_graph = parse_call_chain(backtrace, thread_bt, crash_frame)
    call_chain_llm = to_llm_input(call_chain_graph)

    result: dict = {
        # 基础崩溃信息
        "signal":     signal,
        "crash_type": classify_crash(signal, registers),

        # 崩溃现场
        "crash_frame":   crash_frame,
        "backtrace":     backtrace,
        "registers":     registers,
        "stack_memory":  extract_stack_memory(sections["rsp"], sections["rbp"]),

        # 线程
        "threads":    extract_threads(sections["info_threads"]),
        "threads_bt": thread_bt,

        # 环境
        "shared_libs":     extract_dpdk_lib_status(sections["shared"]),
        "dpdk_subsystems": extract_dpdk_subsystem(sections["bt_full"]),

        # 崩溃地址类型
        "crash_address_type": extract_crash_address_type(registers, sections["mappings"]),

        # call chain
        "call_chain_graph": call_chain_graph.to_dict(),
        "call_chain_llm":   call_chain_llm,
    }

    result["warnings"] = _collect_warnings(result)
    return result