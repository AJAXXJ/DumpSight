import datetime
from agent.graphs.fault_analysis.graph import get_fault_analysis_graph
from agent.main import run_fault_analyse
from server.repository.client_redis import (
    get_dpdk_core_info,
    get_dpdk_core_info_by_key,
)
from server.repository.client_repository import (
    add_client_info,
    get_all_client_info,
    get_client_info,
    update_client_heartbeat,
)
from server.repository.core_repository import add_core_info


def client_status_service(client_id):
    """
    Check the status of a client by its ID.
    """
    return get_client_info(client_id)


def client_register_service(client_register_info):
    """
    Register a new client with the server.
    """
    client_id = client_register_info.get("client_id")
    environment = client_register_info.get("environment")

    if get_client_info(client_id):
        raise ValueError(f"Client {client_id} already exists")

    add_client_info(client_id, environment)


def client_heartbeat_service(heartbeat_info):
    """
    Process a heartbeat from a client.
    """
    client_id = heartbeat_info.get("client_id")

    if not client_id:
        raise ValueError("Missing required fields in heartbeat_info")

    update_client_heartbeat(client_id)


def client_core_analyse_service(crash_info):
    """
    Analyse a client crash event.
    """
    client_id = crash_info.get("client_id")
    pid = crash_info.get("pid")
    key = crash_info.get("key")

    if not client_id or not pid or not key:
        raise ValueError("Missing required fields in crash_info")

    if not get_client_info(client_id):
        raise ValueError("Client not found")

    # 触发分析流程
    core_info = get_dpdk_core_info_by_key(key)

    graph = get_fault_analysis_graph()
    analyse_time, result = run_fault_analyse(
        graph, {"client_id": client_id, "pid": pid, "timestamp": key.split(":")[-1]}
    )

    report = result["report"]

    total_time = core_info.get("process_time") + analyse_time

    add_core_info(
        client_id,
        pid,
        key.split(":")[-1],
        report,
        core_info.get("process_time"),
        analyse_time,
        total_time,
    )


def is_client_alive(client, timeout=30):
    """
    判断客户端是否存活
    """
    last = client.get("update_time")
    if not last:
        return False

    # 如果是字符串 → 转 datetime
    if isinstance(last, str):
        last = datetime.datetime.fromisoformat(last)

    # 如果没有时区 → 补 UTC
    if last.tzinfo is None:
        last = last.replace(tzinfo=datetime.timezone.utc)

    # 当前时间（UTC + 带时区）
    now = datetime.datetime.now(datetime.timezone.utc)

    return (now - last).total_seconds() < timeout


def client_get_all_alive_info(timeout=30):
    """
    获取存活客户端
    """
    clients = get_all_client_info()

    return [c for c in clients if is_client_alive(c, timeout)]
