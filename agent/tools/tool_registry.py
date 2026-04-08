from __future__ import annotations
import logging
from functools import lru_cache
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


class Tool:
    """单个工具对象，封装 invoke 方法"""
    def __init__(self, func: Callable[..., Any], name: str | None = None) -> None:
        self.func = func
        self.name = name or func.__name__
        logger.debug("Tool created | name=%s", self.name)

    def invoke(self, params: dict[str, Any]) -> Any:
        """调用工具"""
        try:
            result = self.func(**params)
            logger.debug("Tool invoked | name=%s params=%s", self.name, params)
            return result
        except Exception as exc:
            logger.exception("Tool '%s' invoke failed", self.name)
            raise


class ToolRegistry:
    """管理所有工具对象"""
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        logger.info("ToolRegistry initialized")
        self._register()

    def register(self, name: str, func: Callable[..., Any]) -> Tool:
        """注册工具函数，返回 Tool 实例"""
        tool = Tool(func=func, name=name)
        self._tools[name] = tool
        logger.debug("Registered tool | name=%s", name)
        return tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: '{name}'. Available: {sorted(self._tools.keys())}")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def invalidate(self) -> None:
        self.get_cached.cache_clear()
        logger.info("ToolRegistry cache invalidated")

    @lru_cache(maxsize=64)
    def get_cached(self, name: str) -> Tool:
        """带缓存获取 Tool 对象"""
        return self.get(name)
    
    def _register(self):
        pass


# 默认单例
_default_registry: ToolRegistry | None = None


def get_tools() -> ToolRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    tools = get_tools()

    # 定义原始工具函数
    def fetch_client_info(os: str = "linux") -> dict:
        return {"os": os, "cpu": "x86_64"}

    def fetch_dpdk_info(version: str = "23.08") -> dict:
        return {"version": version}

    # 注册工具
    tools.register("client_info", fetch_client_info)
    tools.register("dpdk_info", fetch_dpdk_info)

    # 调用工具
    client_info = tools.get("client_info").invoke({"os": "linux"})
    dpdk_info   = tools.get("dpdk_info").invoke({"version": "23.08"})
    print(client_info)
    print(dpdk_info)