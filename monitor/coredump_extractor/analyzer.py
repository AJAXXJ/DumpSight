import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from monitor.coredump_extractor.tools.mismatch_pattern import (
    SymbolQualityAssessor,
    SymbolStatus,
)
from monitor.coredump_extractor.tools.elf_notes import read_elf_notes
from monitor.coredump_extractor.tools.eu_stack import run_and_parse_eu_stack
from tools.common_utils import parse_core_filename

from .extractor.context_parser import SystemContextCollector
from .extractor.meta_parser import GdbOutputParser, classify_crash
from tools.constant import _GDB_COMMANDS, GDB_TIMEOUT, SIGNAL_MAP
from .utils import safe_run


class GdbRunner:
    """构造并执行 GDB batch 命令，返回原始输出。"""

    def __init__(self, timeout: int = GDB_TIMEOUT) -> None:
        self._timeout = timeout

    def run(self, exe_path: str, core_file: str) -> object:
        cmd = ["gdb", "--batch", "--quiet"]

        exe_parent = str(Path(exe_path).resolve().parent)
        ldd_paths = self._ldd_paths(exe_path)

        all_paths = set(ldd_paths)
        all_paths.add(exe_parent)
        cmd.extend(["-ex", f"set solib-search-path {':'.join(all_paths)}"])

        for c in _GDB_COMMANDS:
            cmd.extend(["-ex", c])

        cmd.append(exe_path)
        cmd.append(core_file)

        return safe_run(cmd, timeout=self._timeout)

    @staticmethod
    def _ldd_paths(exe_path: str) -> list[str]:
        result = subprocess.run(
            ["ldd", exe_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        paths = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if "=>" not in line:
                continue
            parts = line.split("=>")
            if len(parts) < 2:
                continue
            lib_path = parts[1].strip().split("(")[0].strip()
            if os.path.isabs(lib_path) and os.path.exists(lib_path):
                paths.add(os.path.dirname(lib_path))
        return list(paths)


class CoreDumpAnalyzer:
    """编排 core dump 分析流程：

    快速路径：eu-stack + ELF notes + 系统上下文采集并行（~3-5s）
    GDB 作为回退和增强通道。
    """

    def __init__(
        self,
        gdb_runner: GdbRunner | None = None,
        gdb_parser: GdbOutputParser | None = None,
        context_collector: SystemContextCollector | None = None,
        symbol_assessor: SymbolQualityAssessor | None = None,
    ) -> None:
        self._runner = gdb_runner or GdbRunner()
        self._parser = gdb_parser or GdbOutputParser()
        self._collector = context_collector or SystemContextCollector()
        self._assessor = symbol_assessor or SymbolQualityAssessor()

    def analyze(
        self,
        core_file: str,
        exe_path: str,
        log_path: str | None = None,
    ) -> tuple[dict, dict]:
        meta = self._build_meta(core_file)
        pid = meta.get("pid")

        # Phase 1: 快速路径并行 — eu-stack + ELF notes + 上下文采集
        eu_data: dict = {}
        elf_data: dict = {}
        context: dict = {}

        with ThreadPoolExecutor(max_workers=3) as executor:
            eu_future = executor.submit(run_and_parse_eu_stack, core_file, exe_path)
            elf_future = executor.submit(read_elf_notes, core_file)
            ctx_future = executor.submit(self._collector.collect, pid, log_path)

            eu_data = eu_future.result() or {}
            elf_data = elf_future.result() or {}
            context = ctx_future.result()

        if eu_data:
            # 快速路径成功：合并 eu-stack + ELF notes 数据
            parsed = self._merge_fast_path(eu_data, elf_data, meta)
            parsed_status = SymbolStatus.VALID
            parsed_warnings: list[str] = []
        else:
            # 回退到 GDB
            gdb_result = self._runner.run(exe_path, core_file)
            parsed_status, parsed_warnings = self._assessor.assess(
                gdb_result.returncode, gdb_result.stderr
            )
            parsed = self._parser.parse(gdb_result.stdout or "")

        meta.update(
            {
                "parsed_gdb_output": parsed,
                "parsed_status": parsed_status,
                "parsed_warnings": parsed_warnings,
            }
        )

        return meta, context

    # ── 快速路径合并 ───────────────────────────────────────────────────────

    @staticmethod
    def _merge_fast_path(eu_data: dict, elf_data: dict, meta: dict) -> dict:
        """将 eu-stack 输出与 ELF notes 数据合并为 GdbParseResult 兼容格式。"""
        parsed = dict(eu_data)

        # 从 ELF notes 覆盖寄存器
        registers = elf_data.get("registers") or {}
        if registers:
            parsed["registers"] = registers

        # 从 ELF notes 获取信号
        elf_signal_num = elf_data.get("signal")
        if elf_signal_num:
            sig_name = SIGNAL_MAP.get(elf_signal_num, f"SIG_{elf_signal_num}")
            parsed["signal"] = {"name": sig_name, "description": ""}

        # 从 meta 获取信号（文件名解析的优先级更高）
        meta_signal_name = meta.get("signal_name", "UNKNOWN")
        if meta_signal_name != "UNKNOWN":
            parsed["signal"] = {"name": meta_signal_name, "description": ""}

        # 从 ELF notes 获取 faulting_address
        faulting_address = elf_data.get("faulting_address")
        if faulting_address:
            parsed["faulting_address"] = faulting_address

        # 计算 crash_type
        signal_info = parsed.get("signal")
        parsed["crash_type"] = classify_crash(signal_info, registers, faulting_address)

        # 推断 crash_address_type（通过 rip 和 /proc/<pid>/maps，如有）
        if registers.get("rip") and meta.get("pid"):
            parsed["crash_address_type"] = CoreDumpAnalyzer._infer_address_region(
                registers["rip"], str(meta["pid"])
            )

        # 补充 call_chain_llm 中缺少的字段
        llm = parsed.get("call_chain_llm") or {}
        if signal_info:
            llm["signal"] = signal_info.get("name", "")
        llm["faulting_address"] = faulting_address
        parsed["call_chain_llm"] = llm

        return parsed

    @staticmethod
    def _infer_address_region(rip: str, pid: str) -> dict | None:
        """通过 /proc/<pid>/maps 推断 rip 所属的内存区域。"""
        try:
            addr = int(rip, 16)
        except (ValueError, TypeError):
            return None
        try:
            with open(f"/proc/{pid}/maps", "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 2:
                        continue
                    rng = parts[0].split("-")
                    if len(rng) != 2:
                        continue
                    try:
                        start = int(rng[0], 16)
                        end = int(rng[1], 16)
                    except ValueError:
                        continue
                    if start <= addr < end:
                        name = parts[-1] if len(parts) > 5 else ""
                        region_type = _classify_region(name)
                        return {
                            "region": name or "anonymous",
                            "start": rng[0],
                            "end": rng[1],
                            "type": region_type,
                        }
        except (OSError, FileNotFoundError):
            pass
        return None

    @staticmethod
    def _build_meta(core_file: str) -> dict:
        file_info = parse_core_filename(os.path.basename(core_file))
        return {
            "pid": file_info.get("pid"),
            "tid": file_info.get("tid"),
            "signal": file_info.get("signal"),
            "signal_name": file_info.get("signal_name", "UNKNOWN"),
        }


def _classify_region(name: str) -> str:
    """复制自 meta_parser._classify_region，避免循环导入。"""
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


# ── Backward-compatible free functions ────────────────────────────────────

_default_analyzer = CoreDumpAnalyzer()


def analyze_core_dump(core_file: str, exe_path: str, log_path: str | None = None) -> tuple[dict, dict]:
    return _default_analyzer.analyze(core_file, exe_path, log_path)


def analyze_core(core_file: str, exe_path: str) -> dict:
    meta, _ = _default_analyzer.analyze(core_file, exe_path, log_path=None)
    return meta


def parse_core(exe_path: str, core_file: str) -> object:
    return _default_analyzer._runner.run(exe_path, core_file)


def build_meta(core_file: str) -> dict:
    return CoreDumpAnalyzer._build_meta(core_file)


def extract_ldd_paths(exe_path: str) -> list[str]:
    return GdbRunner._ldd_paths(exe_path)
