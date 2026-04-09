import time
from flask import current_app
from agent.graphs.fault_analysis.graph import get_fault_analysis_graph
from server.repository.client_redis import get_dpdk_core_info
from server.repository.client_repository import add_client_info, get_client_info, update_client_heartbeat
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
    
    update_client_heartbeat(client_id)


def client_core_analyse_service(crash_info):
    """
    Analyse a client crash event.
    """
    client_id = crash_info.get('client_id')
    pid = crash_info.get('pid')
    timestamp = crash_info.get('timestamp')

    if not client_id or not pid or not timestamp:
        raise ValueError("Missing required fields in crash_info")
    
    if not get_client_info(client_id):
        raise ValueError("Client not found")

    # 触发分析流程
    core_info = get_dpdk_core_info(client_id, pid, timestamp)

    start_time = time.time()
    graph = get_fault_analysis_graph()
    # TODO write to OSS
    crash_report = graph.invoke({
        "client_id": client_id,
        "pid": pid,
        "timestamp": timestamp
    })
    end_time = time.time()
    
    analyse_time = round(end_time - start_time, 4)
    total_time = core_info.get("process_time") + analyse_time

    add_core_info(client_id, crash_report, core_info.get("process_time"), analyse_time, total_time)