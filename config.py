import os
import sys
import yaml
from dataclasses import dataclass, field


def get_exe_dir() -> str:
    """Get the directory of the current executable or script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


EXE_DIR = get_exe_dir()
sys.path.append(EXE_DIR)

# Single source of truth for all defaults
DEFAULT_CONFIG: dict = {
    "dpdk_batch_ttl": 300,
    "encryption_key": "XUT",
    "schedule_heartbeat_interval": 10,
    "schedule_clean_crashed_core_interval": 600,
    "tmp_dir": "tmp",
    "logs_dir": "logs",
    "core_dump_dir": "core_dumps",
    "core_info_dir": "core_infos",
    "client_id": "",
    "client_secret": "",
    "server_url": "",
    "redis_host": "localhost",
    "redis_port": 6379,
    "redis_db": 0,
    "redis_password": "",
}


@dataclass
class DumpSightConfig:
    """Configuration for DumpSight, loaded from a YAML file."""

    config_file: str = "config.yaml"

    # Runtime fields (populated after __post_init__)
    dpdk_batch_ttl: int = field(init=False)
    encryption_key: str = field(init=False)
    schedule_heartbeat_interval: int = field(init=False)
    schedule_clean_crashed_core_interval: int = field(init=False)
    tmp_dir: str = field(init=False)
    logs_dir: str = field(init=False)
    core_dump_dir: str = field(init=False)
    core_info_dir: str = field(init=False)
    client_id: str = field(init=False)
    client_secret: str = field(init=False)
    server_url: str = field(init=False)
    redis_host: str = field(init=False)
    redis_port: int = field(init=False)
    redis_db: int = field(init=False)
    redis_password: str = field(init=False)

    def __post_init__(self):
        self.config_file = os.path.join(EXE_DIR, self.config_file)
        if not os.path.exists(self.config_file):
            self._create_default_config()
        self._load_config()
        self._ensure_dirs()

    def _load_config(self) -> None:
        """Load YAML and apply values to instance attributes."""
        with open(self.config_file, "r") as f:
            self._config_data: dict = yaml.safe_load(f) or {}

        data = {**DEFAULT_CONFIG, **self._config_data}  # file overrides defaults

        # Resolve paths
        tmp = os.path.join(EXE_DIR, data["tmp_dir"])
        self.tmp_dir = tmp
        self.logs_dir = os.path.join(tmp, data["logs_dir"])
        self.core_dump_dir = os.path.join(tmp, data["core_dump_dir"])
        self.core_info_dir = os.path.join(tmp, data["core_info_dir"])

        # Remaining scalar fields
        for key in (
            "dpdk_batch_ttl",
            "encryption_key",
            "schedule_heartbeat_interval",
            "schedule_clean_crashed_core_interval",
            "client_id",
            "client_secret",
            "server_url",
            "redis_host",
            "redis_port",
            "redis_db",
            "redis_password",
        ):
            setattr(self, key, data[key])

    def _create_default_config(self) -> None:
        """Write default config YAML if none exists."""
        with open(self.config_file, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        print(f"Created default config: {self.config_file}")

    def _ensure_dirs(self) -> None:
        """Create required runtime directories."""
        for d in (self.tmp_dir, self.logs_dir, self.core_dump_dir, self.core_info_dir):
            os.makedirs(d, exist_ok=True)

    def _flush(self) -> None:
        """Persist current _config_data to disk."""
        with open(self.config_file, "w") as f:
            yaml.dump(self._config_data, f, default_flow_style=False)

    def set_config(self, key: str, value) -> None:
        """
        Update a config value both in memory and on disk.
        Unknown keys are accepted (stored in YAML but not as typed attributes).
        """
        self._config_data[key] = value
        if hasattr(self, key):
            setattr(self, key, value)
        self._flush()

    def reload(self) -> None:
        """Re-read the YAML file (useful if edited externally)."""
        self._load_config()


config = DumpSightConfig()
