import functools
import time
from datetime import datetime
import schedule
from inotify_simple import INotify, flags
from monitor.live_monitor import check_devbind_on_anomaly
from monitor.monitor_manager import get_monitor_manager
from tools.utils import parse_core_filename
from tools.logger import logger
from monitor.request import client_heartbeat, report_crash


def monitor_core(config):
    """
    Watch the specified directory for new core dump files and process them using DumpSight.
    """
    inotify = INotify()
    wd = inotify.add_watch(config.core_dump_dir, flags.CLOSE_WRITE)

    try:
        while True:
            for event in inotify.read():
                filename = event.name
                if (
                    not filename.startswith("core")
                    or filename.endswith(".meta.json")
                    or filename.endswith(".context.json")
                ):
                    continue

                # exe pid
                parsed_info = parse_core_filename(filename)
                pid = str(parsed_info["pid"])

                # set the status of the pid to "crashed"
                monitor_info = get_monitor_manager().set_pid_status(pid, "crashed")

                if monitor_info is None:
                    logger.warning(
                        f"PID {pid} not found in {config.monitor_file}. Skipping core dump processing."
                    )
                    continue

                logger.info(f"Core dump detected: {filename}, PID: {pid}")

                # get the path of the exe, core dump and the log file
                exe_path = monitor_info["exe_path"]
                core_path = f"{config.core_dump_dir}/{filename}"
                log_path = monitor_info["log_path"]
                timestamp = time.time()
                
                if exe_path != parsed_info["exe_path"]:
                    logger.warning(f"Executable path mismatch for PID {pid}")
                    continue

                # device binding status
                device_binding_status = check_devbind_on_anomaly()

                # TODO 接入分析模块
                logger.info(
                    f"Processing core dump for PID {pid}: {exe_path}: {core_path}: {log_path}"
                )

                preprocess_info = {
                    "pid": pid,
                    "timestamp": timestamp,
                    "datetime": datetime.now(),
                    "exe_name": monitor_info["exe_name"],
                    "exe_path": exe_path,
                    "file_prefix": monitor_info["file_prefix"],
                    "instance": monitor_info["instance"],
                    "device_binding_status": device_binding_status,
                }

                # set core preprocess info in redis
                get_monitor_manager().set_preprocess_core_info(preprocess_info)
                # report crash to server
                # report_crash(config, pid, timestamp)


    finally:
        inotify.rm_watch(wd)


def clean_crashed_core(config):
    """
    Clean up core dump files for processes that have been marked as "crashed" in the monitor file.
    """
    clean_status_info_partial = functools.partial(
        get_monitor_manager().clean_status_info, "crashed"
    )

    schedule.every(config.schedule_clean_crashed_core_interval).seconds.do(
        clean_status_info_partial
    )

    while True:
        schedule.run_pending()
        time.sleep(1)


def send_client_heartbeat(config, dpdk_monitor=None):
    """
    Send heartbeat requests to the server at regular intervals to indicate that the client is alive.
    """

    def _heartbeat_with_flush():
        batch = dpdk_monitor.flush() if dpdk_monitor is not None else []
        if batch:
            get_monitor_manager().flush_dpdk_batch(batch)
        # client_heartbeat(config)

    schedule.every(config.schedule_heartbeat_interval).seconds.do(_heartbeat_with_flush)

    while True:
        schedule.run_pending()
        time.sleep(1)
