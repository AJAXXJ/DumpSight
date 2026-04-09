import requests
from monitor.live_monitor import environment
from tools.encrypt_decrypt import encrypt
from tools.logger import logger


def client_status(config):
    """
    Check the status of the client by sending a request to the server.
    """
    try:
        status_url = config.server_url + "/api/client/status"
        response = requests.get(status_url, params={"client_id": config.client_id})

        if response.status_code == 200:
            status_info = response.json()
            logger.info(f"Client status: {status_info}")
        else:
            logger.error(
                f"Failed to get client status with status code: {response.status_code}"
            )

    except Exception as e:
        logger.error(f"Error during client status check: {e}")


def client_register(config):
    """
    Register the client with the server.
    """
    try:
        register_url = config.server_url + "/api/client/register"

        payload = {
            "client_id": config.client_id,
            "client_secret": encrypt(config.secret_key, config.encryption_key),
            "environment": environment(),
        }

        response = requests.post(register_url, json=payload)

        if response.status_code == 200:
            logger.info("Client registered successfully.")
        else:
            raise Exception(
                f"Client registration failed with status code: {response.status_code}"
            )
    except Exception as e:
        logger.error(f"Error during client registration: {e}")


def client_heartbeat(config):
    """
    Send heartbeat requests to the server at regular intervals to indicate that the client is alive.
    """
    try:
        heartbeat_url = config.server_url + "/api/client/heartbeat"

        payload = {
            "client_id": config.client_id,
            "status": "alive",
        }

        response = requests.post(heartbeat_url, json=payload)

        if response.status_code == 200:
            logger.info("Heartbeat sent successfully.")
        else:
            logger.error(f"Heartbeat failed with status code: {response.status_code}")

    except Exception as e:
        logger.error(f"Error during heartbeat: {e}")


def report_crash(config, pid, timestamp):
    """
    Report a client crash event to the server for core analysis.
    """
    try:
        core_analyse_url = config.server_url + "/api/client/report_crash"

        payload = {"client_id": config.client_id, "pid": pid, "timestamp": timestamp}

        response = requests.post(core_analyse_url, json=payload, timeout=5)

        if response.status_code == 200:
            logger.info(
                f"Crash reported: client={config.client_id}, pid={pid}, timestamp={timestamp}"
            )
        else:
            logger.error(
                f"Core analysis failed with status code: {response.status_code}"
            )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error during core analysis: {e}")
