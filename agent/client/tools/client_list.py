import json
from typing import Any, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from server.repository.client_repository import get_all_client_info


class ClientListTool(BaseTool):
    name: str = "client_list_tool"
    description: str = "获取系统所有的客户端ID列表"

    def _run(self) -> str:
        client_list = get_all_client_info()
        response = [client["client_id"] for client in client_list]
        return json.dumps(response, ensure_ascii=False)

    async def _arun(self) -> str:
        return self._run()
