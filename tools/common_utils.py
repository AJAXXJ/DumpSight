import os
import sys
import click
from tools.constant import SIGNAL_MAP
from tools.logger import logger
from datetime import datetime

def check_root():
    """
    Check if the current user is root.
    """
    if os.geteuid() != 0:
        click.echo("This command must be run as root.", err=True)
        sys.exit(1)
        

def parse_core_filename(filename):
    """
    parse core.<exe>.<pid>.<tid>.<signal>.<timestamp>.<encoded_path>
    """
    parts = filename.split(".", 6)

    if len(parts) < 7:
        logger.warning(f"Invalid core filename: {filename}")

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
        "exe_exists": os.path.exists(exe_path)
    }


def format_datetime(dt, fmt="%Y-%m-%d %H:%M:%S"):
    if dt is None:
        return None

    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt)

    # 字符串
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            try:
                dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return dt

    # 最终统一格式化
    if hasattr(dt, "strftime"):
        return dt.strftime(fmt)

    return dt