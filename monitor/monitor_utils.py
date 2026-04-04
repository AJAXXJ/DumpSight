import os
import json
from pathlib import Path
from monitor.constant import SIGNAL_MAP
from tools.logger import logger


def exists_monitor_list(monitor_file):
    """
    Check if the monitor file exists.
    """
    if not os.path.exists(monitor_file):
        with open(monitor_file, "w") as f:
            json.dump([], f)


def read_monitor_list(monitor_file):
    """
    Read the monitor list from the monitor file.
    """
    with open(monitor_file, "r") as f:
        monitor_list = json.load(f)

    return monitor_list

def read_monitor_list_by_status(monitor_file, status):
    """
    Read the monitor list from the monitor file filtered by status.
    """
    monitor_list = read_monitor_list(monitor_file)
    return [(pid, info) for pid, info in monitor_list if info.get("status") == status]


def add_monitor_info(monitor_file, pid, info):
    """
    Add monitor information to the monitor file.
    """
    monitor_list = read_monitor_list(monitor_file)
    # ensure that the monitor list does not contain the same pid with non-running status
    monitor_list = exists_pid_info(monitor_list, str(pid))
    
    monitor_list.append((str(pid), info))

    with open(monitor_file, "w") as f:
        json.dump(monitor_list, f, indent=4)


def exists_pid_info(monitor_list, pid):
    """
    Check if the monitor list contains the same pid with non-running status.
    """
    info = get_pid_info(monitor_list, pid)
    if info is not None and info.get("status") != "running":
        return del_pid_info(monitor_list, pid)
    return monitor_list


def get_pid_info(monitor_list, pid):
    """
    Get the information for a specific PID from the monitor list.
    """
    return next((info for p, info in monitor_list if p == pid), None)


def del_pid_info(monitor_list, pid):
    """
    Delete the information for a specific PID from the monitor list.
    """
    return [(p, info) for p, info in monitor_list if p != pid]


def set_pid_status(monitor_file, pid, status):
    """
    Set the status for a specific PID in the monitor file.
    """
    monitor_list = read_monitor_list(monitor_file)
    info = get_pid_info(monitor_list, pid)
    if info is None:
        logger.warning(f"PID {pid} not found in the monitor list.")
        return
    info["status"] = status
    with open(monitor_file, "w") as f:
        json.dump(monitor_list, f, indent=4)
    
    return info
        

def clean_status_info(config, status):
    """
    Clean the information for all PIDs with a specific status from the monitor file.
    """
    monitor_list = read_monitor_list(config.monitor_file)
    to_remove = [(p, info) for p, info in monitor_list if info.get("status") == status]
    to_keep   = [(p, info) for p, info in monitor_list if info.get("status") != status]

    for pid, info in to_remove:
        # del core dump files
        if config.core_dump_dir:
            for core_file in Path(config.core_dump_dir).glob(f"core.*.{pid}.*"):
                try:
                    core_file.unlink()
                    logger.info(f"Deleted core file: {core_file}")
                except OSError as e:
                    logger.error(f"Failed to delete core file {core_file}: {e}")

        # del log files
        log_path = info.get("log_path")
        if log_path:
            try:
                Path(log_path).unlink(missing_ok=True)
                logger.info(f"Deleted log file: {log_path}")
            except OSError as e:
                logger.error(f"Failed to delete log file {log_path}: {e}", err=True)

    with open(config.monitor_file, "w") as f:
        json.dump(to_keep, f, indent=4)


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
