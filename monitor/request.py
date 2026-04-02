import time
import requests
from tools.logger import logger

def client_register():
    """
    Register the client with the server.
    """
    pass


def client_hearbeat(config):
    """
    Send heartbeat requests to the server at regular intervals to indicate that the client is alive.
    """
    try:
        heartbeat_url = config.heartbeat_url
        
        while True:
            response = requests.post(heartbeat_url, json={'status': 'alive'})
            
            if response.status_code == 200:
                logger.info("Heartbeat sent successfully.")
            else:
                logger.error(f"Heartbeat failed with status code: {response.status_code}")
                
            time.sleep(config.heartbeat_interval)
            
    except Exception as e:
        logger.error(f"Error during heartbeat: {e}")
