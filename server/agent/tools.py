from langchain.tools import tool

from server.repository.client_redis import get_dpdk_core_info, get_dpdk_info, get_dpdk_log_both
from server.repository.client_repository import get_client_info

@tool
def get_client_info_tool(client_id: str) -> dict:
    """
    {
        "description": "获取指定客户端的环境信息",
        "args": {
            "client_id": {
                "type": "str",
                "description": "客户端的唯一 ID，用于识别客户端实例"
            }
        },
        "returns": {
            "type": "dict",
            "description": "包含客户端环境信息的字典，例如操作系统、CPU、内存等"
        }
    }
    """
    return get_client_info(client_id)


@tool
def get_dpdk_info_tool(client_id: str, pid: int) -> dict:
    """
    {
        "description": "获取指定客户端和进程的 DPDK 应用信息",
        "args": {
            "client_id": {
                "type": "str",
                "description": "客户端的唯一 ID"
            },
            "pid": {
                "type": "int",
                "description": "DPDK 进程的进程 ID"
            }
        },
        "returns": {
            "type": "dict",
            "description": "DPDK 应用的运行状态信息，例如端口状态、队列信息等"
        }
    }
    """
    return get_dpdk_info(client_id, pid)


@tool
def get_dpdk_core_info_tool(client_id: str, pid: int, timestamp: str) -> dict:
    """
    {
        "description": "获取指定客户端、进程和时间点的 DPDK 核心状态信息",
        "args": {
            "client_id": {
                "type": "str",
                "description": "客户端的唯一 ID"
            },
            "pid": {
                "type": "int",
                "description": "DPDK 进程 ID"
            },
            "timestamp": {
                "type": "str",
                "description": "时间戳，格式 'YYYY-MM-DD HH:MM:SS'，用于获取特定时间点的数据"
            }
        },
        "returns": {
            "type": "dict",
            "description": "DPDK 核心的详细信息，包括 CPU 核心绑定、使用率、负载情况等"
        }
    }
    """
    return get_dpdk_core_info(client_id, pid, timestamp)


@tool
def get_dpdk_log_both_tool(client_id: str, pid: int, minutes: int = 15) -> str:
    """
    {
        "description": "获取指定客户端和进程最近一段时间的 DPDK 日志",
        "args": {
            "client_id": {
                "type": "str",
                "description": "客户端的唯一 ID"
            },
            "pid": {
                "type": "int",
                "description": "DPDK 进程 ID"
            },
            "minutes": {
                "type": "int",
                "description": "获取日志的时间范围（分钟），默认值为 15",
                "optional": true
            }
        },
        "returns": {
            "type": "str",
            "description": "拼接后的日志内容，包括标准输出和标准错误信息"
        }
    }
    """
    return get_dpdk_log_both(client_id, pid, minutes)