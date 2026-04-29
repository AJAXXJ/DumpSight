import datetime
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_redis import get_dpdk_instances_by_client
from server.repository.client_repository import get_client_info


class DpdkListToolInput(BaseModel):
    client_id: str = Field(description="客户端 ID")


class DpdkListTool(BaseTool):
    name: str = "dpdk_list_tool"
    description: str = "获取指定ID客户端的所有DPDK实例进程列表"
    args_schema: Type[BaseModel] = DpdkListToolInput

    def _run(self, client_id: str) -> str:
        client_info = get_client_info(client_id)
        if client_info is None:
            return f"系统不存在ID为 {client_id} 的客户端"
        
        dpdk_info_list = get_dpdk_instances_by_client(client_id)
        if dpdk_info_list is None:
            return f"客户端 {client_id} 不存在任何正在运行或者已经停止的进程"

        response = []
        for dpdk_info in dpdk_info_list:
            response.append(
                {
                    "pid": dpdk_info["pid"],
                    "file_prefix": dpdk_info["file_prefix"],
                    "instance": dpdk_info["instance"],
                    "status": dpdk_info["status"],
                    "start_time": datetime.datetime.fromtimestamp(
                        dpdk_info["start_time"]
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        return json.dumps(response, ensure_ascii=False)

    async def _arun(self, client_id: str) -> str:
        return self._run(client_id)
