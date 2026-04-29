import datetime
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_redis import get_dpdk_info
from server.repository.client_repository import get_client_info
from server.repository.core_repository import get_core_info
from server.service.dashboard_service import dashboard_render_report_service



class ReportInfoToolInput(BaseModel):
    client_id: str = Field(description="客户端 ID")
    dpdk_pid: str = Field(description="DPDK 进程 PID")
    timestamp: int = Field(description="查询时间戳，单位为秒")
    

class ReportInfoTool(BaseTool):
    name: str = "report_info_tool"
    description: str = "查询指定客户端的DPDK崩溃分析报告具体信息。"
    args_schema: Type[BaseModel] = ReportInfoToolInput

    def _run(self, client_id: str, dpdk_pid: str, timestamp: int) -> str:
        
        core_info = get_core_info(client_id, dpdk_pid, timestamp)
        if core_info is None:
            return f"客户端 {client_id} 的 PID 为 {dpdk_pid} 的进程在时间戳 {timestamp} 没有崩溃记录"
        response = {
            "report": core_info["report"],
        }
        return json.dumps(response, ensure_ascii=False)

    async def _arun(self, client_id: str, dpdk_pid: str, timestamp: int) -> str:
        return self._run(client_id, dpdk_pid, timestamp)
