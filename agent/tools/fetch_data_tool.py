from server.repository.client_redis import get_dpdk_core_info, get_dpdk_info, get_dpdk_log
from server.repository.client_repository import get_client_info


def client_info_tool(client_id):
    return get_client_info(client_id)

def dpdk_info_tool(client_id, pid):
    return get_dpdk_info(client_id, pid)

def core_info_tool(client_id, pid, timestamp):
    return get_dpdk_core_info(client_id, pid, timestamp)

def log_1s_tool(client_id, pid):
    return get_dpdk_log(client_id, pid, "1s")

def log_5s_tool(client_id, pid):
    return get_dpdk_log(client_id, pid, "5s")