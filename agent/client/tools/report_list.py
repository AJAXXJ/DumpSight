import datetime
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_redis import get_dpdk_info
from server.repository.client_repository import get_client_info
from server.repository.core_repository import get_core_info, get_core_list
from server.service.dashboard_service import dashboard_render_report_service




    

class ReportListTool(BaseTool):
    name: str = "report_list_tool"
    description: str = "查询所有DPDK进程崩溃分析报告列表。"

    def _run(self) -> str:
        
        core_list = get_core_list()
        response = []
        for core in core_list:
            response.append({
                "client_id": core["client_id"],
                "pid": core["pid"],
                "timestamp": core["timestamp"],
            })
        return json.dumps(response, ensure_ascii=False)

    async def _arun(self) -> str:
        return self._run()
