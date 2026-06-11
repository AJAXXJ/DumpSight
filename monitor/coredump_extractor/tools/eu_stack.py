"""通过 eu-stack (elfutils) 获取线程回溯，替代 GDB 的 bt 命令。

eu-stack 直接使用 libdw 读取 core 文件的 unwind 表，不需要完整 DWARF 符号加载，
在大型 core dump 上比 GDB 快 10-50 倍。
"""

import re
import subprocess
from typing import Optional

from monitor.coredump_extractor.tools.parse_call_chain import (
    CallChainParser,
    CallChainResult,
    DPDKFrameClassifier,
    DPDKCrashPatternMatcher,
)
from tools.constant import _GDB_COMMANDS, IDLE_FRAMES, SIGNAL_MAP

_EU_STACK_BIN = "eu-stack"
_EU_STACK_MAX_FRAMES = 64
_EU_STACK_TIMEOUT = 30  # eu-stack 不应该超过 30s

# 解析 eu-stack 帧行 — 分两步：先匹配前缀 "#N  0xADDR [rest]"，再从剩余部分拆出函数名和模块路径
# 格式：
#   #N  0xADDR     func_name - /path/to/module
#   #N  0xADDR - /path/to/module            （无符号时函数名为空）
_RE_EUSTACK_FRAME_PREFIX = re.compile(
    r"^#(\d+)\s+(0x[0-9a-fA-F]+)\s*(.*)$"
)

# 源码行（缩进 4+ 空格）
_RE_SOURCE_LINE = re.compile(r"^\s{4,}(\S+):(\d+)(?::(\d+))?")

# 内联帧（子缩进，函数名开头）
_RE_INLINE_FRAME = re.compile(r"^\s{4,}(\w[\w:]*)\(.*\)\s*$")

# eu-stack 模块列表输出（-l 标志）
_RE_MODULE_LINE = re.compile(
    r"^\s*(0x[0-9a-f]+)-(0x[0-9a-f]+)\s+"
    r"(0x[0-9a-f]+)\s+"
    r"(\S+)\s+"                     # ELF path
    r"(\S+)?\s*"                    # optional debug file
    r"(\S+)?\s*$",                  # optional build-id
    re.MULTILINE,
)

# 空函数名（无符号）
_NO_FUNC = frozenset({"", "??", "unknown"})

# 噪音帧函数名
_IDLE_TOKENS: frozenset[str] = frozenset(
    filter(None, (re.sub(r"[\s_()]+", "", (x or "").lower()) for x in IDLE_FRAMES))
) | frozenset({
    "read", "libcread", "epollwait", "pthreadcondwait",
    "pthreadcondtimedwait", "futexwait", "nanosleep", "clocknanosleep",
    "socketlistener", "mphandle", "libcaccept",
})


def _norm_name(s: str) -> str:
    return re.sub(r"[\s_()]+", "", (s or "").lower())


def _is_idle_frame(func_name: str) -> bool:
    t = _norm_name(func_name)
    return any(tok in t for tok in _IDLE_TOKENS) if t else False


class EuStackParser:
    """运行 eu-stack 并将输出转换为 GDB 兼容格式，使下游 CallChainParser 无感切换。"""

    def __init__(
        self,
        call_chain_parser: CallChainParser | None = None,
    ) -> None:
        self._chain_parser = call_chain_parser or CallChainParser()
        self._classifier = DPDKFrameClassifier()
        self._matcher = DPDKCrashPatternMatcher()

    def run_and_parse(
        self,
        core_path: str,
        exe_path: str,
    ) -> dict:
        """运行 eu-stack 并返回与 GdbParseResult 兼容的 dict。"""
        raw = self._run(core_path, exe_path)
        if raw is None:
            return {}  # eu-stack 失败，调用方应回退到 GDB

        threads_bt = self._parse_output(raw)

        if not threads_bt:
            return {}

        backtrace = threads_bt.get("1", threads_bt.get(list(threads_bt.keys())[0] if threads_bt else "1", []))

        crash_frame = self._extract_crash_frame(backtrace)

        call_chain_result = self._chain_parser.parse(
            backtrace, threads_bt, crash_frame
        )

        return self._build_result(
            threads_bt, backtrace, crash_frame, call_chain_result
        )

    # ── 执行 eu-stack ──────────────────────────────────────────────────────

    @staticmethod
    def _run(core_path: str, exe_path: str) -> Optional[str]:
        cmd = [
            _EU_STACK_BIN,
            "--core", core_path,
            "--exec", exe_path,
            "-s", "-m",             # 源码 + 模块信息
            "-n", str(_EU_STACK_MAX_FRAMES),
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=_EU_STACK_TIMEOUT,
            )
            if r.returncode > 1:  # 0=ok, 1=partial, 2=fatal
                return None
            return r.stdout or ""
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None

    # ── 解析 eu-stack 输出 ─────────────────────────────────────────────────

    def _parse_output(self, raw: str) -> dict[str, list[str]]:
        """将 eu-stack 文本输出转换为 {tid: [GDB格式帧字符串, ...]}"""
        threads: dict[str, list[str]] = {}
        current_tid: Optional[str] = None
        current_frames: list[str] = []
        pending_source: Optional[str] = None  # 上一帧的源码信息

        for line in raw.splitlines():
            tid_match = re.match(r"^TID\s+(\d+):", line)
            if tid_match:
                if current_tid is not None and current_frames:
                    threads[current_tid] = self._filter_frames(current_frames)
                current_tid = tid_match.group(1)
                current_frames = []
                pending_source = None
                continue

            source_match = _RE_SOURCE_LINE.match(line)
            if source_match and current_frames:
                # 将源码信息附加到上一帧
                pending_source = f"{source_match.group(1)}:{source_match.group(2)}"
                prev = current_frames[-1]
                if " at " not in prev:
                    current_frames[-1] = f"{prev} at {pending_source}"
                continue

            frame_match = _RE_EUSTACK_FRAME_PREFIX.match(line)
            if frame_match:
                rest = frame_match.group(3).strip()
                func, _ = self._split_func_module(rest)
                frame_str = self._frame_to_gdb_format(
                    idx=frame_match.group(1),
                    addr=frame_match.group(2),
                    func=func,
                )
                current_frames.append(frame_str)
                pending_source = None

        if current_tid is not None and current_frames:
            threads[current_tid] = self._filter_frames(current_frames)

        return threads

    @staticmethod
    def _split_func_module(rest: str) -> tuple[str, str]:
        """从 eu-stack 帧剩余部分拆分函数名和模块路径。

        格式:
          func_name - /path/to/module   → (func_name, /path/to/module)
          - /path/to/module             → ("", /path/to/module)  无符号
        """
        rest = rest.strip()
        if rest.startswith("- "):
            return "", rest[2:].strip()
        if " - " in rest:
            idx = rest.rindex(" - ")
            func = rest[:idx].strip()
            module = rest[idx + 3:].strip()
            return func, module
        return rest, ""

    @staticmethod
    def _frame_to_gdb_format(idx: str, addr: str, func: str) -> str:
        func = func.strip()
        if func in _NO_FUNC:
            func = "??"
        return f"#{idx}  {addr} in {func} ()"

    @staticmethod
    def _filter_frames(frames: list[str]) -> list[str]:
        """去重同一地址的帧（eu-stack -i 可能为内联展开重复输出同一 PC）"""
        if not frames:
            return frames
        result = [frames[0]]
        seen_addrs: set[str] = set()
        m = re.match(r"^#\d+\s+(0x[0-9a-f]+)", frames[0])
        if m:
            seen_addrs.add(m.group(1))
        for f in frames[1:]:
            m = re.match(r"^#\d+\s+(0x[0-9a-f]+)", f)
            addr = m.group(1) if m else ""
            if addr not in seen_addrs:
                seen_addrs.add(addr)
                result.append(f)
        return result

    # ── Crash frame ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_crash_frame(backtrace: list[str]) -> Optional[dict]:
        if not backtrace:
            return None
        first = backtrace[0]
        m = re.match(
            r"^#\d+\s+(0x[0-9a-fA-F]+)?\s*(?:in\s+)?(\S+)"
            r"(?:\s*\(.*?\))?(?:\s+at\s+(\S+):(\d+))?",
            first,
        )
        if not m:
            return None
        func = m.group(2)
        if func in ("??", ""):
            return None
        return {
            "function": func,
            "file": m.group(3),
            "line": m.group(4),
            "has_debuginfo": m.group(3) is not None,
        }

    # ── 构建与 GdbParseResult 兼容的 dict ──────────────────────────────────

    def _build_result(
        self,
        threads_bt: dict[str, list[str]],
        backtrace: list[str],
        crash_frame: Optional[dict],
        call_chain_result: CallChainResult,
    ) -> dict:
        """构建与 GdbOutputParser.parse() 输出兼容的 dict。"""
        from monitor.coredump_extractor.tools.parse_call_chain import to_llm_input

        call_chain_graph = call_chain_result.to_dict()
        callstack_names = {n.name for n in call_chain_result.main_thread.callstack}

        crash_layer = self._classifier.classify(call_chain_result.crash_function)
        dpdk_subsystems = self._detect_subsystems(callstack_names)

        # 线程摘要
        thread_summary = self._build_thread_summary(threads_bt)

        call_chain_llm = to_llm_input(
            call_chain_result,
            raw_meta={
                "signal_name": "未知",
                "crash_address_region": "未知",
                "threads": thread_summary,
                "faulting_address": None,
            },
        )

        return {
            "signal": None,
            "crash_type": "unknown",
            "crash_frame": crash_frame,
            "backtrace": backtrace,
            "registers": {},
            "stack_memory": {},
            "threads": thread_summary,
            "threads_bt": threads_bt,
            "shared_libs": {"dpdk_lib_missing": False, "found_libs": [], "missing_libs": []},
            "dpdk_subsystems": dpdk_subsystems,
            "crash_address_type": None,
            "faulting_address": None,
            "crash_locals": {},
            "warnings": [],
            "call_chain_graph": call_chain_graph,
            "call_chain_llm": call_chain_llm,
        }

    # ── 线程摘要 ───────────────────────────────────────────────────────────

    def _build_thread_summary(self, threads_bt: dict[str, list[str]]) -> dict:
        total = len(threads_bt)
        tid1 = list(threads_bt.keys())[0] if threads_bt else "1"
        crashed_bt = threads_bt.get(tid1, threads_bt.get("1", []))
        crashed_top = self._bt_top(crashed_bt)

        crashed = {
            "id": tid1,
            "lwp": tid1,
            "bt_top": crashed_top,
            "role": "crashed",
        } if crashed_top else None

        idle_count = 0
        abnormal = []
        for tid, bt in threads_bt.items():
            if tid == tid1:
                continue
            top = self._bt_top(bt)
            if _is_idle_frame(top):
                idle_count += 1
            elif top:
                abnormal.append({
                    "id": tid,
                    "lwp": tid,
                    "bt_top": top,
                    "role": "unknown",
                })

        return {
            "total": total,
            "crashed": crashed,
            "abnormal": abnormal,
            "idle": max(idle_count, 0),
        }

    @staticmethod
    def _bt_top(frames: list[str]) -> str:
        if not frames:
            return ""
        m = re.match(r"^#\d+\s+(?:0x[0-9a-f]+\s+in\s+)?(\S+)", frames[0])
        return m.group(1) if m else ""

    # ── DPDK 子系统检测 ────────────────────────────────────────────────────

    @staticmethod
    def _detect_subsystems(func_names: set[str]) -> list[str]:
        from tools.constant import SUBSYSTEMS
        combined = " ".join(func_names)
        return [
            name
            for name, pattern in SUBSYSTEMS.items()
            if re.search(pattern, combined)
        ]


# 模块级快捷函数
_default_eu_parser = EuStackParser()


def run_and_parse_eu_stack(core_path: str, exe_path: str) -> dict:
    return _default_eu_parser.run_and_parse(core_path, exe_path)
