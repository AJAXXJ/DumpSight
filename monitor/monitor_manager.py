import json
from pathlib import Path
from tools.logger import logger
from tools.redis_util import redis_util
from dumpsight import config

class RedisMonitorManager:
    
    def __init__(self, config):
        self.config = config
        self.client_id = str(config.client_id)
        self._ensure_monitor_client()

    def _ensure_monitor_client(self):
        """Ensure the monitor client key exists in Redis."""
        if not redis_util.exists(self.client_id):
            redis_util.set(self.client_id, json.dumps({}))

    def read_monitor_list(self):
        """Read the full monitor list from Redis (returns a dict)."""
        monitor_data = redis_util.get(self.client_id)
        if monitor_data:
            try:
                return json.loads(monitor_data)
            except json.JSONDecodeError:
                logger.error("Failed to decode monitor list JSON from Redis")
        return {}

    def read_monitor_list_by_status(self, status):
        """Return list of (pid, info) tuples filtered by status."""
        monitor_list = self.read_monitor_list()
        return [
            (pid, info)
            for pid, info in monitor_list.items()
            if isinstance(info, dict) and info.get("status") == status
        ]

    def get_pid_info(self, pid):
        """Get info for a specific PID."""
        monitor_list = self.read_monitor_list()
        return monitor_list.get(str(pid))

    def add_monitor_info(self, pid, info):
        """Add or update monitor information for a PID.
        If the same PID exists with non-running status, remove it first."""
        pid = str(pid)
        monitor_list = self.read_monitor_list()

        # Remove non-running PID if exists
        info_existing = monitor_list.get(pid)
        if info_existing and info_existing.get("status") != "running":
            monitor_list.pop(pid)

        monitor_list[pid] = info
        redis_util.set(self.client_id, json.dumps(monitor_list))

    def del_pid_info(self, pid):
        """Delete monitor information for a PID."""
        pid = str(pid)
        monitor_list = self.read_monitor_list()
        monitor_list.pop(pid, None)
        redis_util.set(self.client_id, json.dumps(monitor_list))

    def set_pid_status(self, pid, status):
        """Set the status of a specific PID."""
        pid = str(pid)
        monitor_list = self.read_monitor_list()
        info = monitor_list.get(pid)
        if not info:
            logger.warning(f"PID {pid} not found in the monitor list.")
            return None

        info["status"] = status
        monitor_list[pid] = info
        redis_util.set(self.client_id, json.dumps(monitor_list))
        return info

    def clean_status_info(self, status):
        """Clean all PIDs with a specific status and remove their core/log files."""
        monitor_list = self.read_monitor_list()
        to_remove = {pid: info for pid, info in monitor_list.items() if info.get("status") == status}

        for pid, info in to_remove.items():
            # Delete core dump files
            core_dir = getattr(self.config, "core_dump_dir", None)
            if core_dir:
                for core_file in Path(core_dir).glob(f"core.*.{pid}.*"):
                    try:
                        core_file.unlink()
                        logger.info(f"Deleted core file: {core_file}")
                    except OSError as e:
                        logger.error(f"Failed to delete core file {core_file}: {e}")

            # Delete log files
            log_path = info.get("log_path")
            if log_path:
                try:
                    Path(log_path).unlink(missing_ok=True)
                    logger.info(f"Deleted log file: {log_path}")
                except OSError as e:
                    logger.error(f"Failed to delete log file {log_path}: {e}")

            # Remove PID from monitor list
            monitor_list.pop(pid, None)

        redis_util.set(self.client_id, json.dumps(monitor_list))


monitor_manager = RedisMonitorManager(config)