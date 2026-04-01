from inotify_simple import INotify, flags

from monitor.monitor_utils import set_pid_status
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
                pid = filename.split(".")[1]
                # set the status of the pid to "crashed"
                set_pid_status(config.monitor_file, pid, "crashed")
                logger.info(f"Core dump detected: {filename}, PID: {pid}")
                # TODO 接入分析模块
    finally:
        inotify.rm_watch(wd)
