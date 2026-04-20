import json
import time
from pathlib import Path
from tools.logger import logger
from tools.redis_util import get_redis_util, RedisConfig
from config import config
import threading


class RedisMonitorManager:

    def __init__(self, config):
        self.config = config
        self.client_id = str(config.client_id)
        self.info_prefix = f"{self.client_id}:info"

        self.redis = get_redis_util(RedisConfig.from_config(config))

    def _info_key(self, pid):
        return f"{self.info_prefix}:{pid}"

    def read_monitor_list(self):
        """
        Read the full monitor list from Redis (returns a dict of pid -> info).
        """
        kv = self.redis.scan_with_values(f"{self.info_prefix}:*")
        result = {}
        for key, data in kv.items():
            if not data:
                continue
            try:
                pid = key.split(":")[-1]
                result[pid] = json.loads(data)
            except json.JSONDecodeError:
                logger.error(f"Failed to decode monitor info JSON for key {key}")
        return result

    def read_monitor_list_by_status(self, status):
        """Return list of (pid, info) tuples filtered by status."""
        monitor_list = self.read_monitor_list()
        return [
            (pid, info)
            for pid, info in monitor_list.items()
            if isinstance(info, dict) and info.get("status") == status
        ]

    def get_pid_info(self, pid):
        """
        Get info for a specific PID.
        """
        data = self.redis.get(self._info_key(pid))
        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode monitor info JSON for PID {pid}")
            return None

    def add_monitor_info(self, pid, info):
        """
        Add or update monitor information for a PID.
        If the same PID exists with non-running status, remove it first.
        """
        pid = str(pid)
        existing = self.get_pid_info(pid)

        if existing:
            if existing.get("status") == "crashed":
                return
            if existing.get("status") != "running":
                self.redis.delete(self._info_key(pid))

        self.redis.set(self._info_key(pid), json.dumps(info))

    def update_status_if_running(self, pid, new_status):
        """只有当前是 running 才更新状态"""
        pid = str(pid)
        existing = self.get_pid_info(pid)
        if existing and existing.get("status") == "running":
            existing["status"] = new_status
            self.redis.set(self._info_key(pid), json.dumps(existing))
            return True
        return False

    def set_pid_status(self, pid, status):
        """
        Set the status of a specific PID.
        """
        pid = str(pid)
        info = self.get_pid_info(pid)
        if not info:
            logger.warning(f"PID {pid} not found in the monitor list.")
            return None

        info["status"] = status
        self.redis.set(self._info_key(pid), json.dumps(info))
        return info

    def clean_status_info(self, status):
        """
        Clean all PIDs with a specific status and remove their core/log files.
        """
        monitor_list = self.read_monitor_list()
        to_remove = [
            (pid, info)
            for pid, info in monitor_list.items()
            if info.get("status") == status
        ]

        keys_to_delete = []
        for pid, info in to_remove:
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

            keys_to_delete.append(self._info_key(pid))

        # Batch delete all Redis keys at once
        if keys_to_delete:
            self.redis.delete_many(keys_to_delete)

    def set_preprocess_core_info(self, pid, preprocess_info):
        """
        Set preprocess dump core info in redis.
        """
        pid = str(pid)
        timestamp = int(preprocess_info.get("core_timestamp"))
        ttl = getattr(self.config, "core_info_ttl", None)

        key = f"{self.client_id}:core:{pid}:{timestamp}"
        self.redis.set(key, json.dumps(preprocess_info), expire=ttl)
        return key

    def flush_dpdk_batch(self, batch):
        """
        Write flushed DPDK batch to Redis.
        """
        ttl = getattr(self.config, "dpdk_batch_ttl", None)

        for record in batch:
            pid = record.get("pid")
            record_type = record.get("type")
            timestamp_second = int(record.get("timestamp", time.time()))

            if not pid or record_type not in ("1s", "5s"):
                continue

            key = f"{self.client_id}:log:{pid}:{record_type}:{timestamp_second}"
            self.redis.set(key, json.dumps(record), expire=ttl)

    def read_running_instances_info(self):
        """
        Read information about running DPDK instances from the monitor file.
        """
        instances = []
        running_apps_info = self.read_monitor_list_by_status(status="running")
        for pid, info in running_apps_info:
            instances.append(
                {
                    "pid": int(pid) if pid is not None else None,
                    "exe_name": info.get("exe_name"),
                    "file_prefix": info.get("file_prefix"),
                    "instance": (
                        int(info["instance"]) if info.get("instance") is not None else 0
                    ),
                }
            )
        return instances


_monitor_manager = None
_monitor_lock = threading.Lock()


def get_monitor_manager() -> RedisMonitorManager:
    global _monitor_manager
    if _monitor_manager is None:
        with _monitor_lock:
            if _monitor_manager is None:
                _monitor_manager = RedisMonitorManager(config)
    return _monitor_manager
