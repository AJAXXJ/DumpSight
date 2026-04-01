import os
import sys
import json


EXC_DIR = os.path.dirname(__file__)
sys.path.append(EXC_DIR)

class DumpSightConfig:
    """
    Configuration class for DumpSight.
    """

    def __init__(self):
        # monitor file
        self.monitor_file = os.path.join(EXC_DIR, "monitor-dpdk.json")

        if not os.path.exists(self.monitor_file):
            with open(self.monitor_file, 'w') as f:
                json.dump([], f)

        # Define paths for logs and core dumps
        self.tmp_dir = os.path.join(EXC_DIR, "tmp")
        self.logs_dir = os.path.join(self.tmp_dir, "logs")
        # self.core_dump_dir = os.path.join(self.tmp_dir, "core_dumps")
        self.core_dump_dir = "./"

        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        # os.makedirs(self.core_dump_dir, exist_ok=True)