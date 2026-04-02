import os
import sys
import json


def get_exe_dir():
    """
    Get the directory of the current executable or script.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))
    

EXC_DIR = get_exe_dir()
sys.path.append(EXC_DIR)


class DumpSightConfig:
    """
    Configuration class for DumpSight.
    """

    def __init__(self):
        # request
        self.server_url = "http://localhost:8000"
        self.register_url = f"{self.server_url}/register"
        self.heartbeat_url = f"{self.server_url}/heartbeat"

        self.heartbeat_interval = 60  # seconds
        # schedule
        self.schedule_clean_crashed_core_interval = 600  # seconds

        # monitor file
        self.monitor_file = os.path.join(EXC_DIR, "monitor-dpdk.json")

        if not os.path.exists(self.monitor_file):
            with open(self.monitor_file, 'w') as f:
                json.dump([], f)

        # Define paths for logs and core dumps
        self.tmp_dir = os.path.join(EXC_DIR, "tmp")
        self.logs_dir = os.path.join(self.tmp_dir, "logs")
        self.core_dump_dir = os.path.join(self.tmp_dir, "core_dumps")

        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.core_dump_dir, exist_ok=True)