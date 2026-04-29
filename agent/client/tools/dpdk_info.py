import datetime
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_redis import get_dpdk_info
from server.repository.client_repository import get_client_info



class DpdkInfoToolInput(BaseModel):
    client_id: str = Field(description="客户端 ID")
    dpdk_pid: str = Field(description="DPDK 进程 PID")
    

class DpdkInfoTool(BaseTool):
    name: str = "dpdk_info_tool"
    description: str = "查询指定客户端和DPDK进程的当前运行信息，包括状态、启动参数和日志位置。"
    args_schema: Type[BaseModel] = DpdkInfoToolInput

    def _run(self, client_id: str, dpdk_pid: str) -> str:
        client_info = get_client_info(client_id)
        if client_info is None:
            return f"系统不存在ID为 {client_id} 的客户端"
        dpdk_info = get_dpdk_info(client_id, dpdk_pid)
        if dpdk_info is None:
            return f"客户端 {client_id} 不存在 PID 为 {dpdk_pid} 的进程"
        response = {
            **dpdk_info,
            "start_time": datetime.datetime.fromtimestamp(
                    dpdk_info["start_time"]
                ).strftime("%Y-%m-%d %H:%M:%S")
        }
        return json.dumps(response, ensure_ascii=False)

    async def _arun(self, client_id: str, dpdk_pid: str) -> str:
        return self._run(client_id, dpdk_pid)
