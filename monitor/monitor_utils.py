import os
import json


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

def add_monitor_info(monitor_file, pid, info):
    """
    Add monitor information to the monitor file.
    """
    monitor_list = read_monitor_list(monitor_file)
    # ensure that the monitor list does not contain the same pid with non-running status
    monitor_list = exists_pid_info(monitor_list, pid)
    
    monitor_list.append((pid, info))

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
    if info is not None:
        info["status"] = status
        add_monitor_info(monitor_file, pid, info)