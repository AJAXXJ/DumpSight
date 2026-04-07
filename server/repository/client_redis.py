import json
import time
from tools.logger import logger
from server.tools.redis_util import get_redis_util

def get_dpdk_info(client_id, pid):
    """
    Get monitor info for a specific PID.
    Key format: {client_id}:info:{pid}
    """
    key = f"{client_id}:info:{pid}"
    data = get_redis_util().get(key)
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.error(f"Failed to decode dpdk info JSON for client {client_id} pid {pid}")
        return None


def get_dpdk_core_info(client_id, pid, timestamp):
    """
    Get all core dump info for a specific PID, sorted by timestamp.
    Key format: {client_id}:core:{pid}:{timestamp}
    """
    key = f"{client_id}:core:{pid}:{timestamp}"
    data = get_redis_util().get(key)
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.error(f"Failed to decode dpdk core info JSON for client {client_id} pid {pid}")
        return None

def get_dpdk_log(client_id, pid, record_type, minutes=15):
    """
    Get DPDK log data for a specific PID and type within the last N minutes.
    record_type: "1s" or "5s"
    """
    now = int(time.time())
    start = now - minutes * 60

    keys = [
        f"{client_id}:log:{pid}:{record_type}:{ts}"
        for ts in range(start, now + 1)
    ]

    kv = get_redis_util().get_many(keys)

    result = []
    for data in kv.values():
        try:
            result.append(json.loads(data))
        except json.JSONDecodeError:
            logger.error(f"Failed to decode dpdk log JSON for pid {pid} type {record_type}")
            continue

    return sorted(result, key=lambda x: x.get("timestamp", 0))


def get_dpdk_log_both(client_id, pid, minutes=15):
    """
    Get both 1s and 5s DPDK log data for a specific PID in a single pipeline call.
    """
    now = int(time.time())
    start = now - minutes * 60
    timestamps = range(start, now + 1)

    keys_1s = [f"{client_id}:log:{pid}:1s:{ts}" for ts in timestamps]
    keys_5s = [f"{client_id}:log:{pid}:5s:{ts}" for ts in timestamps]

    kv = get_redis_util().get_many(keys_1s + keys_5s)

    result_1s, result_5s = [], []
    for key, data in kv.items():
        try:
            record = json.loads(data)
            if ":1s:" in key:
                result_1s.append(record)
            else:
                result_5s.append(record)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode dpdk log JSON for key {key}")
            continue

    return {
        "1s": sorted(result_1s, key=lambda x: x.get("timestamp", 0)),
        "5s": sorted(result_5s, key=lambda x: x.get("timestamp", 0)),
    }