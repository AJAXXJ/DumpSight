import os
from pathlib import Path
import subprocess

from monitor.coredump_extractor.tools.mismatch_pattern import assess_symbol_status
from tools.common_utils import parse_core_filename

from .extractor.context_parser import parse_gdb_context
from .extractor.meta_parser import parse_gdb_output
from tools.constant import _GDB_COMMANDS, GDB_TIMEOUT
from .utils import safe_run


def extract_ldd_paths(exe_path):
    """
    解析动态链接库路径
    """
    result = subprocess.run(
        ["ldd", exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    paths = set()

    for line in result.stdout.splitlines():
        line = line.strip()

        # 跳过 linux-vdso 这种
        if "=>" not in line:
            continue

        parts = line.split("=>")
        if len(parts) < 2:
            continue

        right = parts[1].strip()

        # 取路径部分（去掉地址）
        lib_path = right.split("(")[0].strip()

        if os.path.isabs(lib_path) and os.path.exists(lib_path):
            paths.add(os.path.dirname(lib_path))

    return list(paths)


def parse_core(exe_path, core_file):
    """
    构建 gdb 命令并运行，返回原始结果
    """
    cmd = ["gdb", "--batch", "--quiet"]
    # 获取动态链接库路径
    exe_parent = str(Path(exe_path).resolve().parent)

    ldd_paths = extract_ldd_paths(exe_path)

    all_paths = set(ldd_paths)
    all_paths.add(exe_parent)

    cmd.extend(["-ex", f"set solib-search-path {':'.join(all_paths)}"])

    for c in _GDB_COMMANDS:
        cmd.extend(["-ex", c])

    cmd.append(exe_path)
    cmd.append(core_file)

    return safe_run(cmd, timeout=GDB_TIMEOUT)


def build_meta(core_file):
    """
    构造 meta 基础字段
    """
    file_info = parse_core_filename(os.path.basename(core_file))

    return {
        "pid": file_info.get("pid"),
        "tid": file_info.get("tid"),
        "signal": file_info.get("signal"),
        "signal_name": file_info.get("signal_name", "UNKNOWN"),
    }


def analyze_core(core_file, exe_path):
    """
    编排 gdb 解析流程并返回 meta dict
    """
    meta = build_meta(core_file)
    parsed_info = parse_core(exe_path, core_file)

    parsed_status, parsed_warnings = assess_symbol_status(
        parsed_info.returncode, parsed_info.stderr
    )

    parsed = parse_gdb_output(parsed_info.stdout or "")

    meta.update(
        {
            "parsed_gdb_output": parsed,
            "parsed_status": parsed_status,
            "parsed_warnings": parsed_warnings,
        }
    )

    return meta


def analyze_core_dump(core_file, exe_path, log_path):
    """
    统一编排入口：返回 meta/context 两类数据
    """
    meta = analyze_core(core_file, exe_path)
    context = parse_gdb_context(meta.get("pid"), {}, log_path=log_path)
    return meta, context
