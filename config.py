import os
import sys
import json
import yaml


def get_exe_dir():
    """
    Get the directory of the current executable or script.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


EXC_DIR = get_exe_dir()
sys.path.append(EXC_DIR)

DEFAULT_CONFIG = {
    "encryption_key": "XUT",
    "schedule_heartbeat_interval": 10,
    "schedule_clean_crashed_core_interval": 600,
    "tmp_dir": "tmp",
    "logs_dir": "tmp/logs",
    "core_dump_dir": "tmp/core_dumps",
}


class DumpSightConfig:
    """
    Configuration class for DumpSight.
    """

    def __init__(self, config_file="config.yaml"):
        self.config_file = os.path.join(EXC_DIR, config_file)

        if not os.path.exists(self.config_file):
            self.create_default_config()

        self.load_config()

        os.makedirs(self.tmp_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.core_dump_dir, exist_ok=True)

    def load_config(self):
        """
        Loads configuration from the YAML file.
        """
        with open(self.config_file, "r") as f:
            config_data = yaml.safe_load(f)

        # Assign the loaded config values to the instance attributes
        self.server_url = config_data.get("server_url", "http://localhost:8000")
        self.heartbeat_interval = config_data.get("heartbeat_interval", 60)
        self.schedule_clean_crashed_core_interval = config_data.get(
            "schedule_clean_crashed_core_interval", 600
        )
        self.tmp_dir = os.path.join(EXC_DIR, config_data.get("tmp_dir", "tmp"))
        self.logs_dir = os.path.join(self.tmp_dir, config_data.get("logs_dir", "logs"))
        self.core_dump_dir = os.path.join(
            self.tmp_dir, config_data.get("core_dump_dir", "core_dumps")
        )

    def create_default_config(self):
        """
        Creates a default configuration file if it does not exist.
        """
        with open(self.config_file, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        print(f"{self.config_file} created with default configuration.")

    def set_config(self, variable_name, variable_value):
        """
        Sets or updates a variable in the config. If the variable exists, it updates the value.
        If the variable doesn't exist, it creates the variable with the provided value.
        """
        self.config_data[variable_name] = variable_value
        setattr(self, variable_name, variable_value)
        self.update_config_file()

    def update_config_file(self):
        """
        Writes the current configuration data back to the YAML file.
        """
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config_data, f, default_flow_style=False)