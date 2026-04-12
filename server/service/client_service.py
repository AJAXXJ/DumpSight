from flask import current_app
from agent.graphs.fault_analysis.graph import get_fault_analysis_graph
from agent.graphs.live_monitor.graph import get_realtime_monitor_graph
from agent.main import run_fault_anlyse, run_realtime_monitor
from server.repository.client_redis import (
    get_client_running_instances,
    get_dpdk_core_info,
)
from server.repository.client_repository import (
    add_client_info,
    get_client_info,
    update_client_heartbeat,
)
from server.repository.core_repositiry import add_core_info
from server.tools.encrypt_decrypt import decrypt


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
    client_secret = client_register_info.get("client_secret")
    environment = client_register_info.get("environment")

    if current_app.config["SECRET_KEY"] != decrypt(client_secret):
        raise ValueError("Client secret does not match!")

    add_client_info(client_id, environment)


def client_heartbeat_service(heartbeat_info):
    """
    Process a heartbeat from a client.
    """
    client_id = heartbeat_info.get("client_id")

    if not client_id:
        raise ValueError("Missing required fields in heartbeat_info")

    # 触发日志分析
    instances = get_client_running_instances(client_id)

    if instances:
        graph = get_realtime_monitor_graph()
        for instance in instances:
            run_realtime_monitor(
                graph=graph,
                initial_state={"client_id": client_id, "pid": instance.get("pid")},
                alert_handler=None,
                fault_handler=None,
            )

    update_client_heartbeat(client_id)


def client_core_analyse_service(crash_info):
    """
    Analyse a client crash event.
    """
    client_id = crash_info.get("client_id")
    pid = crash_info.get("pid")
    timestamp = crash_info.get("timestamp")

    if not client_id or not pid or not timestamp:
        raise ValueError("Missing required fields in crash_info")

    if not get_client_info(client_id):
        raise ValueError("Client not found")

    # 触发分析流程
    core_info = get_dpdk_core_info(client_id, pid, timestamp)

    graph = get_fault_analysis_graph()
    analyse_time, result = run_fault_anlyse(
        graph, {"client_id": client_id, "pid": pid, "timestamp": timestamp}
    )

    md_report = result["md_report"]
    json_report = result["json_report"]

    total_time = core_info.get("process_time") + analyse_time

    add_core_info(
        client_id, json_report, core_info.get("process_time"), analyse_time, total_time
    )
