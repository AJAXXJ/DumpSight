from server.repository.client_redis import get_dpdk_core_info, get_dpdk_info, get_dpdk_log
from server.repository.client_repository import get_client_info


def client_info_tool(inputs):
    """
    Retrieves client information based on the provided client ID.

    Args:
        inputs (dict): A dictionary containing the key 'client_id' to identify the client.

    Returns:
        dict: Information about the client retrieved from the get_client_info function.
    """
    client_id = inputs["client_id"]
    return get_client_info(client_id)


def dpdk_info_tool(inputs):
    """
    Retrieves DPDK (Data Plane Development Kit) information for a given client and process ID (PID).

    Args:
        inputs (dict): A dictionary containing the keys 'client_id' and 'pid' to identify the client and process.

    Returns:
        dict: DPDK information related to the client and process ID retrieved from the get_dpdk_info function.
    """
    client_id = inputs["client_id"]
    pid = inputs["pid"]
    return get_dpdk_info(client_id, pid)


def core_info_tool(inputs):
    """
    Retrieves DPDK core information for a specific client, process ID, and timestamp.

    Args:
        inputs (dict): A dictionary containing 'client_id', 'pid', and 'timestamp' for retrieving the core info.

    Returns:
        dict: Core information of the DPDK instance at the given timestamp retrieved from the get_dpdk_core_info function.
    """
    client_id = inputs["client_id"]
    pid = inputs["pid"]
    timestamp = inputs["timestamp"]
    return get_dpdk_core_info(client_id, pid, timestamp)


def log_1s_tool(inputs):
    """
    Retrieves DPDK log data in 1-second intervals for a given client, process ID, and duration.

    Args:
        inputs (dict): A dictionary containing 'client_id', 'pid', and optionally 'seconds' (default 900) for the log duration.

    Returns:
        dict: DPDK log data for the specified 1-second intervals retrieved from the get_dpdk_log function.
    """
    client_id = inputs["client_id"]
    pid = inputs["pid"]
    seconds = inputs.get("seconds", 900)  # Default to 900 seconds if not provided
    return get_dpdk_log(client_id, pid, "1s", seconds)


def log_5s_tool(inputs):
    """
    Retrieves DPDK log data in 5-second intervals for a given client, process ID, and duration.

    Args:
        inputs (dict): A dictionary containing 'client_id', 'pid', and optionally 'seconds' (default 900) for the log duration.

    Returns:
        dict: DPDK log data for the specified 5-second intervals retrieved from the get_dpdk_log function.
    """
    client_id = inputs["client_id"]
    pid = inputs["pid"]
    seconds = inputs.get("seconds", 900)  # Default to 900 seconds if not provided
    return get_dpdk_log(client_id, pid, "5s", seconds)