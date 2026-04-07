from main import app
from server.repository.client_redis import get_dpdk_core_info, get_dpdk_info, get_dpdk_log_both
from server.repository.client_repository import get_client_info
from server.tools.encrypt_decrypt import decrypt

def client_status_service(client_id):
    """
    Check the status of a client by its ID.
    """
    pass


def client_register_service(client_register_info):
    """
    Register a new client with the server.
    """

    client_id = client_register_info.get("client_id")
    client_secret = client_register_info.get("client_secret")
    dpdk_context = client_register_info.get("dpdk_context")
    redis_info = client_register_info.get("redis_info")

    
    if app.config["SECRET_KEY"] != decrypt(client_secret):
        raise ValueError("Client secret does not match!")


def client_core_analyse_service(crash_info):
    """
    Analyse a client crash event.
    """
    client_id = crash_info.get('client_id')
    pid = crash_info.get('pid')
    timestamp = crash_info.get('timestamp')

    if not client_id or not pid or not timestamp:
        raise ValueError("Missing required fields in crash_info")
    
    client_info = get_client_info(client_id)
    dpdk_info = get_dpdk_info(client_id, pid)
    core_info = get_dpdk_core_info(client_id, pid, timestamp)
    log_info = get_dpdk_log_both(client_id, pid)



    