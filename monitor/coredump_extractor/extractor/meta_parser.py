import re
from typing import Optional, TypedDict
from monitor.coredump_extractor.tools.parse_call_chain import (
    parse_call_chain,
    to_llm_input,
)
from tools.constant import IDLE_FRAMES, SIGNAL_MAP, SUBSYSTEMS, KEY_REGISTER


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
    role: str  # lcore_worker | interrupt_thread | control_thread | crashed | unknown


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
    faulting_address: Optional[str]
    crash_locals: dict[str, str]
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
_RE_SIGINFO_ADDR = re.compile(r"\$\d+\s*=\s*(0x[0-9a-f]+|\(void\s*\*\)\s*0x[0-9a-f]+|0)")
_RE_LOCAL_VAR = re.compile(r"^(\w+)\s*=\s*(.+)$", re.MULTILINE)
_RE_MAPPING = re.compile(
    r"(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+0x[0-9a-f]+\s*(.*?)$",
    re.MULTILINE,
)
_RE_SHARED_LIB = re.compile(r"(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(Yes|No)\s+(.+\.so\S*)")
_RE_HEX = re.compile(r"0x[0-9a-f]+")

_SECTION_RE_CACHE: dict[str, re.Pattern] = {}

_IDLE_TOKENS: frozenset[str] = frozenset(
    filter(None, (re.sub(r"[\s_()]+", "", (x or "").lower()) for x in IDLE_FRAMES))
) | frozenset(
    {
        "read",
        "libcread",
        "epollwait",
        "pthreadcondwait",
        "pthreadcondtimedwait",
        "futexwait",
        "nanosleep",
        "clocknanosleep",
        "socketlistener",
        "mphandle",
        "libcaccept",
    }
)

_KEY_REGISTER_SET: frozenset[str] = frozenset(KEY_REGISTER)

# Thread role inference: ordered from most-specific to least-specific.
# Each entry is (role_name, set_of_bt_top_tokens_that_imply_this_role).
_THREAD_ROLE_RULES: list[tuple[str, frozenset[str]]] = [
    ("lcore_worker",    frozenset({"rte_eal_remote_launch", "eal_thread_loop", "rte_lcore_main",
                                   "lcore_config", "eal_worker_thread"})),
    ("interrupt_thread", frozenset({"eal_intr_handle_events", "rte_intr_callback_fn",
                                    "epoll_wait", "epollwait", "rte_ctrl_thread_create",
                                    # DPDK telemetry uses Unix socket with recvmsg
                                    "recvmsg", "__recvmsg", "__recvmsg_syscall",
                                    "recvfrom", "__recvfrom_syscall"})),
    ("control_thread",  frozenset({"rte_mp_", "mp_handle", "socketlistener",
                                   "pthreadcondwait", "pthread_cond_wait"})),
]


def _infer_thread_role(is_crashed: bool, bt_top: str) -> str:
    if is_crashed:
        return "crashed"
    normalized = _norm_text(bt_top)
    for role, tokens in _THREAD_ROLE_RULES:
        if any(_norm_text(tok) in normalized for tok in tokens):
            return role
    if _is_idle_frame_text(bt_top):
        return "lcore_worker"
    return "unknown"


_SUBSYSTEM_RES: dict[str, re.Pattern] = {
    name: re.compile(pattern) for name, pattern in SUBSYSTEMS.items()
}

DPDK_LIB_KEYWORDS = [
    "librte_eal",
    "librte_mbuf",
    "librte_ethdev",
    "librte_net",
    "librte_ring",
]


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


def _is_idle_frame_text(text: str) -> bool:
    t = _norm_text(text)
    if not t:
        return False
    return any(tok in t for tok in _IDLE_TOKENS)


def _classify_sigsegv(registers: dict[str, str], faulting_address: Optional[str] = None) -> str:
    # Prefer si_addr (true faulting address) over rdi (which is just an argument)
    if faulting_address is not None:
        try:
            addr = int(faulting_address, 16)
            if addr == 0:
                return "null_ptr_deref"
            if addr < 0x1000:
                return "near_null_deref"
        except ValueError:
            pass
    if registers.get("rdi") == "0x0":
        return "null_pointer_deref"
    if registers.get("rip") == "0x0":
        return "null_function_call"
    return "invalid_memory_access"


_SIGNAL_CLASSIFIERS: dict[str, object] = {
    "SIGSEGV": _classify_sigsegv,
    "SIGBUS": lambda regs, fa=None: "bus_error_alignment",
    "SIGABRT": lambda regs, fa=None: "abort",
    "SIGFPE": lambda regs, fa=None: "floating_point_exception",
    "SIGILL": lambda regs, fa=None: "illegal_instruction",
    "SIGPIPE": lambda regs, fa=None: "broken_pipe",
    "SIGTERM": lambda regs, fa=None: "terminated",
}


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


class GdbOutputParser:
    """
    解析完整 GDB batch 输出，将各 section 转换为结构化崩溃信息。
    每个 extract_* 方法只读取输入，不修改共享状态。
    """

    def parse(self, output: str) -> GdbParseResult:
        signal = self.extract_signal(output)
        sections = self._extract_all_sections(output)
        registers = self.extract_registers(sections["registers"])

        backtrace = self.extract_backtrace(sections["bt_full"], max_frames=10)
        thread_bt = self.extract_all_threads_bt(sections["thread_bt"])
        crash_frame = self.extract_crash_frame(sections["bt_full"])
        faulting_address = self.extract_faulting_address(sections["siginfo"])
        crash_locals = self.extract_locals(sections["locals"])

        call_chain_graph = parse_call_chain(backtrace, thread_bt, crash_frame)
        call_chain_llm = to_llm_input(
            call_chain_graph,
            raw_meta={
                "suggest_rerun_with_debuginfo": len(backtrace) < 3,
                "signal_name": (signal or {}).get("name", "未知"),
                "crash_address_region": (
                    self.extract_crash_address_type(registers, sections["mappings"]) or {}
                ).get("region", "未知"),
                "threads": self.extract_threads(sections["info_threads"]),
                "faulting_address": faulting_address,
            },
            context={},
        )

        result: dict = {
            "signal": signal,
            "crash_type": self.classify_crash(signal, registers, faulting_address),
            "crash_frame": crash_frame,
            "backtrace": backtrace,
            "registers": registers,
            "stack_memory": self.extract_stack_memory(sections["rsp"], sections["rbp"]),
            "threads": self.extract_threads(sections["info_threads"]),
            "threads_bt": thread_bt,
            "shared_libs": self.extract_dpdk_lib_status(sections["shared"]),
            "dpdk_subsystems": self.extract_dpdk_subsystem(sections["bt_full"]),
            "crash_address_type": self.extract_crash_address_type(
                registers, sections["mappings"]
            ),
            "faulting_address": faulting_address,
            "crash_locals": crash_locals,
            "call_chain_graph": call_chain_graph.to_dict(),
            "call_chain_llm": call_chain_llm,
        }

        result["warnings"] = self._collect_warnings(result, crash_frame)
        return result

    # ── Section extraction ─────────────────────────────────────────────────

    def _extract_all_sections(self, output: str) -> dict[str, str]:
        pairs = [
            ("bt_full",      "=== BT_FULL_BEGIN ===",      "=== BT_FULL_END ==="),
            ("info_threads", "=== INFO_THREADS_BEGIN ===",  "=== INFO_THREADS_END ==="),
            ("registers",    "=== REGISTERS_BEGIN ===",     "=== REGISTERS_END ==="),
            ("mappings",     "=== MAPPINGS_BEGIN ===",      "=== MAPPINGS_END ==="),
            ("shared",       "=== SHARED_BEGIN ===",        "=== SHARED_END ==="),
            ("thread_bt",    "=== THREAD_BT_BEGIN ===",     "=== THREAD_BT_END ==="),
            ("rsp",          "=== RSP_BEGIN ===",           "=== RSP_END ==="),
            ("rbp",          "=== RBP_BEGIN ===",           "=== RBP_END ==="),
            ("args",         "=== ARGS_BEGIN ===",          "=== ARGS_END ==="),
            ("siginfo",      "=== SIGINFO_BEGIN ===",       "=== SIGINFO_END ==="),
            ("locals",       "=== LOCALS_BEGIN ===",        "=== LOCALS_END ==="),
            ("frame_info",   "=== FRAME_INFO_BEGIN ===",    "=== FRAME_INFO_END ==="),
        ]
        return {key: self.get_section(output, begin, end) for key, begin, end in pairs}

    def get_section(self, output: str, begin: str, end: str) -> str:
        m = _get_section_re(begin, end).search(output)
        return m.group(1).strip() if m else ""

    # ── Signal ─────────────────────────────────────────────────────────────

    def extract_signal(self, output: str) -> Optional[SignalInfo]:
        m = _RE_SIGNAL.search(output)
        if not m:
            return None
        raw_name = m.group(1).strip()
        if raw_name.isdigit():
            signal_name = SIGNAL_MAP.get(int(raw_name), f"SIG_{raw_name}")
        else:
            signal_name = raw_name
        return {
            "name": signal_name,
            "description": (m.group(2) or "").strip(),
        }

    # ── Crash frame ────────────────────────────────────────────────────────

    def extract_crash_frame(self, bt_full_section: str) -> Optional[CrashFrame]:
        if not bt_full_section:
            return None
        m = _RE_CRASH_FRAME.search(bt_full_section)
        if m:
            func = m.group(1).strip()
            if func in ("??", ""):
                return None
            return {
                "function": func,
                "file": m.group(2),
                "line": m.group(3),
                "has_debuginfo": m.group(2) is not None,
            }
        return None

    # ── Backtrace ──────────────────────────────────────────────────────────

    def extract_backtrace(self, bt_full_section: str, max_frames: int = 30) -> list[str]:
        if not bt_full_section:
            return []
        frames: list[str] = []
        seen_no: set[int] = set()
        for line in bt_full_section.splitlines():
            m = _RE_FRAME_LINE.match(line)
            if not m:
                continue
            no = int(m.group(1))
            if no in seen_no:
                continue
            seen_no.add(no)
            frames.append(f"#{no} {m.group(2).strip()}")
            if len(frames) >= max_frames:
                break
        return frames

    # ── Threads ────────────────────────────────────────────────────────────

    def extract_threads(self, info_threads_section: str) -> ThreadSummary:
        if not info_threads_section:
            return {"total": 0, "crashed": None, "abnormal": [], "idle": 0}

        crashed_thread: Optional[ThreadInfo] = None
        abnormal_threads: list[ThreadInfo] = []
        total = 0

        for m in _RE_THREAD_INFO.finditer(info_threads_section):
            total += 1
            is_crashed = m.group(1).strip() == "*"
            top = m.group(5).strip()
            thread: ThreadInfo = {
                "id": m.group(2),
                "lwp": m.group(4),
                "bt_top": top,
                "role": _infer_thread_role(is_crashed, top),
            }

            if is_crashed:
                crashed_thread = thread
            elif not _is_idle_frame_text(top):
                abnormal_threads.append(thread)

        idle = total - len(abnormal_threads) - (1 if crashed_thread else 0)
        return {
            "total": total,
            "crashed": crashed_thread,
            "abnormal": abnormal_threads,
            "idle": max(idle, 0),
        }

    # ── Faulting address (si_addr) ─────────────────────────────────────────

    def extract_faulting_address(self, siginfo_section: str) -> Optional[str]:
        if not siginfo_section:
            return None
        m = _RE_SIGINFO_ADDR.search(siginfo_section)
        if not m:
            return None
        raw = m.group(1).strip()
        # strip "(void *) " prefix if present
        hex_m = re.search(r"0x[0-9a-f]+", raw)
        if hex_m:
            return hex_m.group(0)
        if raw == "0":
            return "0x0"
        return None

    # ── Crash frame locals / args ──────────────────────────────────────────

    def extract_locals(self, locals_section: str) -> dict[str, str]:
        if not locals_section:
            return {}
        result: dict[str, str] = {}
        for m in _RE_LOCAL_VAR.finditer(locals_section):
            name, value = m.group(1).strip(), m.group(2).strip()
            # skip GDB internal names and frame header lines
            if name in ("frame", "Stack", "Locals", "Arguments") or name.startswith("#"):
                continue
            result[name] = value
        return result

    # ── Registers ──────────────────────────────────────────────────────────

    def extract_registers(self, registers_section: str) -> dict[str, str]:
        if not registers_section:
            return {}
        return {
            k: v
            for k, v in _RE_REGISTER_KV.findall(registers_section)
            if k in _KEY_REGISTER_SET
        }

    # ── Crash address region ────────────────────────────────────────────────

    def extract_crash_address_type(
        self,
        registers: dict[str, str],
        mappings_section: str,
    ) -> Optional[AddressRegion]:
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
                end = int(m.group(2), 16)
            except ValueError:
                continue
            name = m.group(3).strip()
            if start <= addr < end:
                return {
                    "region": name or "anonymous",
                    "start": m.group(1),
                    "end": m.group(2),
                    "type": _classify_region(name),
                }
        return None

    # ── Per-thread backtraces ───────────────────────────────────────────────

    def extract_all_threads_bt(self, thread_bt_section: str) -> dict[str, list[str]]:
        if not thread_bt_section:
            return {}
        raw = self._parse_thread_blocks(thread_bt_section)
        return self._filter_idle_threads(raw)

    def _parse_thread_blocks(self, section: str) -> dict[str, list[str]]:
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

    def _filter_idle_threads(self, raw: dict[str, list[str]]) -> dict[str, list[str]]:
        return {
            tid: frames
            for tid, frames in raw.items()
            if frames and not any(_is_idle_frame_text(f) for f in frames)
        }

    # ── Stack memory ───────────────────────────────────────────────────────

    def extract_stack_memory(
        self,
        rsp_section: str,
        rbp_section: str,
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for label, section in [("rsp", rsp_section), ("rbp", rbp_section)]:
            if section:
                values = _RE_HEX.findall(section)
                if values:
                    result[label] = values[1:]
        return result

    # ── DPDK shared libs ───────────────────────────────────────────────────

    def extract_dpdk_lib_status(self, shared_section: str) -> dict:
        if not shared_section:
            return {
                "dpdk_lib_missing": True,
                "found_libs": [],
                "missing_libs": DPDK_LIB_KEYWORDS,
            }
        found = {lib for lib in DPDK_LIB_KEYWORDS if lib in shared_section}
        missing = [lib for lib in DPDK_LIB_KEYWORDS if lib not in found]
        return {
            "dpdk_lib_missing": len(missing) > 0,
            "found_libs": list(found),
            "missing_libs": missing,
        }

    # ── DPDK subsystem detection ────────────────────────────────────────────

    def extract_dpdk_subsystem(self, bt_full_section: str) -> list[str]:
        if not bt_full_section:
            return []
        return [
            name
            for name, pattern_re in _SUBSYSTEM_RES.items()
            if pattern_re.search(bt_full_section)
        ]

    # ── Crash classification ────────────────────────────────────────────────

    def classify_crash(
        self,
        signal_info: Optional[SignalInfo],
        registers: dict[str, str],
        faulting_address: Optional[str] = None,
    ) -> str:
        if not signal_info:
            return "unknown"
        sig = signal_info.get("name", "")
        handler = _SIGNAL_CLASSIFIERS.get(sig)
        if handler:
            return handler(registers, faulting_address)
        return sig or "unknown"

    # ── Warnings ───────────────────────────────────────────────────────────

    def _collect_warnings(self, result: dict, crash_frame: Optional[CrashFrame]) -> list[str]:
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
            has_source = crash_frame and crash_frame.get("has_debuginfo")
            if not has_source:
                result["suggest_rerun_with_debuginfo"] = True

        threads = result.get("threads", {})
        if threads.get("total", 0) == 0:
            warnings.append("no threads parsed from info_threads section")
        if not result.get("crash_frame"):
            warnings.append("crash frame (#0) not found in bt_full section")

        shared = result.get("shared_libs", {})
        if isinstance(shared, dict) and shared.get("dpdk_lib_missing"):
            missing = shared.get("missing_libs", [])
            warnings.append(f"DPDK shared libs missing: {missing}")

        return warnings


# ── Backward-compatible free functions ────────────────────────────────────

_default_parser = GdbOutputParser()


def parse_gdb_output(output: str) -> GdbParseResult:
    return _default_parser.parse(output)


def get_section(output: str, begin: str, end: str) -> str:
    return _default_parser.get_section(output, begin, end)


def extract_signal(output: str) -> Optional[SignalInfo]:
    return _default_parser.extract_signal(output)


def extract_crash_frame(bt_full_section: str) -> Optional[CrashFrame]:
    return _default_parser.extract_crash_frame(bt_full_section)


def extract_backtrace(bt_full_section: str, max_frames: int = 30) -> list[str]:
    return _default_parser.extract_backtrace(bt_full_section, max_frames)


def extract_threads(info_threads_section: str) -> ThreadSummary:
    return _default_parser.extract_threads(info_threads_section)


def extract_registers(registers_section: str) -> dict[str, str]:
    return _default_parser.extract_registers(registers_section)


def extract_crash_address_type(
    registers: dict[str, str], mappings_section: str
) -> Optional[AddressRegion]:
    return _default_parser.extract_crash_address_type(registers, mappings_section)


def extract_all_threads_bt(thread_bt_section: str) -> dict[str, list[str]]:
    return _default_parser.extract_all_threads_bt(thread_bt_section)


def extract_stack_memory(rsp_section: str, rbp_section: str) -> dict[str, list[str]]:
    return _default_parser.extract_stack_memory(rsp_section, rbp_section)


def extract_dpdk_lib_status(shared_section: str) -> dict:
    return _default_parser.extract_dpdk_lib_status(shared_section)


def extract_dpdk_subsystem(bt_full_section: str) -> list[str]:
    return _default_parser.extract_dpdk_subsystem(bt_full_section)


def classify_crash(
    signal_info: Optional[SignalInfo],
    registers: dict[str, str],
    faulting_address: Optional[str] = None,
) -> str:
    return _default_parser.classify_crash(signal_info, registers, faulting_address)


def extract_faulting_address(siginfo_section: str) -> Optional[str]:
    return _default_parser.extract_faulting_address(siginfo_section)


def extract_locals(locals_section: str) -> dict[str, str]:
    return _default_parser.extract_locals(locals_section)
