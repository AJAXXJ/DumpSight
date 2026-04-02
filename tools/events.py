import functools
import time
import schedule
from inotify_simple import INotify, flags
from monitor.monitor_utils import clean_status_info, parse_core_filename, set_pid_status
from tools.logger import logger


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
                # pid = filename.split(".")[1]
                # set the status of the pid to "crashed"
                monitor_info = set_pid_status(config.monitor_file, pid, "crashed")

                if monitor_info is None:
                    logger.warning(f"PID {pid} not found in {config.monitor_file}. Skipping core dump processing.")
                    continue

                logger.info(f"Core dump detected: {filename}, PID: {pid}")

                # get the path of the exe, core dump and the log file
                exe_path = monitor_info["exe_path"]
                core_path = f"{config.core_dump_dir}/{filename}"
                log_path = monitor_info['log_path']

                if exe_path != parsed_info["exe_path"]:
                    logger.warning(f"Executable path mismatch for PID {pid}")
                    continue

                # TODO 接入分析模块
                logger.info(f"Processing core dump for PID {pid}: {exe_path}: {core_path}: {log_path}")
    finally:
        inotify.rm_watch(wd)


def clean_crashed_core(config):

    """
    Clean up core dump files for processes that have been marked as "crashed" in the monitor file.
    """
    clean_status_info_partial = functools.partial(clean_status_info, config, "crashed")
    
    schedule.every(config.schedule_clean_crashed_core_interval).seconds.do(clean_status_info_partial) 

    while True:
        schedule.run_pending()
        time.sleep(1)

