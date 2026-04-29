import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_repository import get_client_info


class ClientInfoToolInput(BaseModel):
    client_id: str = Field(description="客户端 ID")


class ClientInfoTool(BaseTool):
    name: str = "client_info_tool"
    description: str = "获取客户端信息基于提供的客户端ID"
    args_schema: Type[BaseModel] = ClientInfoToolInput

    def _run(self, client_id: str) -> str:
        client_info = get_client_info(client_id)
        return json.dumps(client_info, ensure_ascii=False)

    async def _arun(self, client_id: str) -> str:
        return self._run(client_id)
