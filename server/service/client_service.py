from main import app
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
