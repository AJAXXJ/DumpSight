import os
from pathlib import Path

from .extractor.context_parser import parse_gdb_context
from .extractor.meta_parser import parse_gdb_output
from .constant import SIGNAL_MAP, GDB_TIMEOUT
from .utils import safe_run


def parse_core_filename(filename):
    """
    解析格式 core.<exe>.<pid>.<tid>.<signal>.<timestamp>.<encoded_path>
    """
    parts = filename.split(".", 6)

    if len(parts) < 7:
        raise ValueError(f"Invalid core filename: {filename}")

    _, exe_name, pid, tid, signal, ts, encoded_path = parts
    exe_path = encoded_path.replace("!", "/")
    if not exe_path.startswith("/"):
        exe_path = "/" + exe_path

    return {
        "exe_name": exe_name,
        "pid": int(pid),
        "tid": int(tid),
        "signal": int(signal),
        "signal_name": SIGNAL_MAP.get(int(signal), "UNKNOWN"),
        "timestamp": int(ts),
        "exe_path": exe_path,
        "exe_exists": os.path.exists(exe_path),
    }


def parse_core(exe_path, core_file):
    """
    解析 core 文件并输出重要信息
    """
    commands = [
        "set print frame-arguments all",      # 调用栈增强

        "echo === INFO_THREADS_BEGIN ===\\n",
        "info threads",
        "echo === INFO_THREADS_END ===\\n",

        "echo === THREAD_BT_BEGIN ===\\n",
        "thread apply all bt 5",              # 所有线程打印调用栈 最多5层
        "echo === THREAD_BT_END ===\\n",

        "echo === BT_FULL_BEGIN ===\\n",
        "bt full",                            # 当前线程深度分析
        "echo === BT_FULL_END ===\\n",

        "echo === REGISTERS_BEGIN ===\\n",
        "info registers",                     # 寄存器分析
        "echo === REGISTERS_END ===\\n",

        "echo === RSP_BEGIN ===\\n",
        "x/4xg $rsp",                         # 查看栈顶内容
        "echo === RSP_END ===\\n",

        "echo === RBP_BEGIN ===\\n",
        "x/4xg $rbp",                         # 查看栈帧基地址
        "echo === RBP_END ===\\n",

        "echo === SHARED_BEGIN ===\\n",
        "info shared",                        # 共享库信息
        "echo === SHARED_END ===\\n",

        "echo === ARGS_BEGIN ===\\n",
        "show args",                          # 启动参数
        "echo === ARGS_END ===\\n",

        "echo === MAPPINGS_BEGIN ===\\n",
        "info proc mappings",                 # 内存布局
        "echo === MAPPINGS_END ===\\n",
    ]

    cmd = ["gdb", "--batch", "--quiet"]
    if exe_path:
        exe_parent = str(Path(exe_path).resolve().parent)
        cmd.extend(["-ex", f"set solib-search-path {exe_parent}"])
    for c in commands:
        cmd.extend(["-ex", c])
    if exe_path:
        cmd.append(exe_path)
    cmd.append(core_file)

    return safe_run(cmd, timeout=GDB_TIMEOUT)


def build_meta(core_file, exe_path=None):
    """
    仅构造 meta 基础字段，不做 IO
    """
    try:
        file_info = parse_core_filename(os.path.basename(core_file))
    except Exception:
        file_info = {
            "exe_name": Path(exe_path).name if exe_path else None,
            "pid": None,
            "tid": None,
            "signal": None,
            "signal_name": "UNKNOWN",
            "timestamp": None,
            "exe_path": exe_path,
            "exe_exists": bool(exe_path and os.path.exists(exe_path)),
        }

    if exe_path:
        file_info["exe_path"] = exe_path
        file_info["exe_exists"] = os.path.exists(exe_path)
        file_info["exe_name"] = file_info.get("exe_name") or Path(exe_path).name

    return {
        "core_file": core_file,
        "exe_name": file_info.get("exe_name"),
        "exe_path": file_info.get("exe_path"),
        "exe_exists": file_info.get("exe_exists", False),
        "signal": file_info.get("signal"),
        "signal_name": file_info.get("signal_name", "UNKNOWN"),
        "tid": file_info.get("tid"),
        "pid": file_info.get("pid"),
        "timestamp": file_info.get("timestamp"),
    }


def assess_symbol_status(returncode, stderr):
    """
    评估符号可信度：
    - ok / mismatch / partial / unknown
    """
    warnings = []
    status = "ok"

    err = (stderr or "").strip()
    err_lower = err.lower()

    # 明确的符号不匹配信号
    mismatch_patterns = [
        "build-id" in err_lower and "does not match core file" in err_lower,
        "wrong library or version mismatch" in err_lower,
    ]
    if any(mismatch_patterns):
        status = "mismatch"
        if "build-id" in err_lower and "does not match core file" in err_lower:
            warnings.append("build_id_mismatch")
        if "wrong library or version mismatch" in err_lower:
            warnings.append("library_version_mismatch")

    # gdb 非零退出，可信度降低
    if returncode is None:
        if status == "ok":
            status = "unknown"
        warnings.append("gdb_returncode_unknown")
    elif returncode != 0:
        if status == "ok":
            status = "partial"
        warnings.append(f"gdb_returncode_{returncode}")

    return status, warnings


def analyze_core(core_file, exe_path=None):
    """
    编排 gdb 解析流程并返回 meta dict（不写文件）
    """
    meta = build_meta(core_file, exe_path=exe_path)
    result = parse_core(meta.get("exe_path"), core_file)

    parsed = parse_gdb_output(result.stdout or "")
    meta["parsed_gdb_output"] = parsed
    meta["gdb"] = {
        "returncode": result.returncode,
        "stderr": (result.stderr or "").strip(),
    }

    symbol_status, symbol_warnings = assess_symbol_status(
        result.returncode,
        result.stderr or "",
    )
    meta["symbol_status"] = symbol_status
    meta["symbol_warnings"] = symbol_warnings

    # shared_libs 语义增强：保留原字段，同时避免 symbol 非 ok 时出现强肯定措辞
    shared_libs = parsed.get("shared_libs")
    consistency = "ok" if symbol_status == "ok" else ("mismatch" if symbol_status == "mismatch" else "unknown")
    if isinstance(shared_libs, dict):
        shared_libs["consistency"] = consistency
        if symbol_status != "ok" and shared_libs.get("info") == "All critical libraries are loaded":
            shared_libs["info"] = "Critical libraries detected, but symbol consistency is not fully reliable"

    return meta


def collect_context(pid, log_path=None):
    """
    编排上下文采集并返回 context dict（不写文件）
    """
    return parse_gdb_context(pid, {}, log_path=log_path)


def analyze_core_dump(core_file, exe_path=None, log_path=None):
    """
    统一编排入口：返回 meta/context 两类数据
    """
    meta = analyze_core(core_file, exe_path=exe_path)
    context = collect_context(meta.get("pid"), log_path=log_path)
    return meta, context