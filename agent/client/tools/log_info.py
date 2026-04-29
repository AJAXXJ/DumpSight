import datetime
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from agent.tools.telemetry_feature_tool import build_llm_features, log_1s_statistic, log_5s_statistic
from server.repository.client_redis import get_dpdk_info, get_dpdk_log
from server.repository.client_repository import get_client_info



class LogInfoToolInput(BaseModel):
    client_id: str = Field(description="客户端 ID")
    dpdk_pid: str = Field(description="DPDK 进程 PID")
    seconds: int = Field(description="指定时间日志区间", gt=0, le=200)
    

class LogInfoTool(BaseTool):
    name: str = "dpdk_log_tool"
    description: str = "查询指定客户端和DPDK进程在给定时间区间内的日志内容，并进行聚合分析，适用于故障排查。"
    args_schema: Type[BaseModel] = LogInfoToolInput

    def _run(self, client_id: str, dpdk_pid: str, seconds: int) -> str:
        client_info = get_client_info(client_id)
        if client_info is None:
            return f"系统不存在ID为 {client_id} 的客户端"
        dpdk_info = get_dpdk_info(client_id, dpdk_pid)
        if dpdk_info is None:
            return f"客户端 {client_id} 不存在 PID 为 {dpdk_pid} 的进程"
        metrics_1s = get_dpdk_log(client_id, dpdk_pid, "1s", seconds) 
        metrics_5s = get_dpdk_log(client_id, dpdk_pid, "5s", seconds)
        if metrics_1s is None and metrics_5s is None:
            return f"客户端 {client_id} 中 进程 {dpdk_pid} 不存在日志信息"
        statistic_1s = log_1s_statistic(metrics_1s)
        statistic_5s = log_5s_statistic(metrics_5s)
        log_feature = build_llm_features(statistic_1s, statistic_5s, metrics_1s)
        return json.dumps(log_feature, ensure_ascii=False)

    async def _arun(self, client_id: str, dpdk_pid: str, seconds: int) -> str:
        return self._run(client_id, dpdk_pid, seconds)
