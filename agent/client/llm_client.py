import logging
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.messages import AIMessageChunk
from agent.client.tools import ALL_TOOLS
from agent.config.llm_factory import get_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "你是一个 DPDK 网络数据平面的智能运维专家，可以使用工具来帮助用户解决问题，请用中文回答。"

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        llm = get_llm(mode="fast")
        _agent = create_agent(
            model=llm,
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )
        logger.info("Agent initialized with %d tools", len(ALL_TOOLS))
    return _agent


def _build_messages(history: list[dict], query: str) -> list[BaseMessage]:
    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant" and msg.get("content"):
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=query))
    return messages


def completion(query: str, history: list[dict] | None = None) -> str:
    try:
        messages = _build_messages(history or [], query)
        result = _get_agent().invoke({"messages": messages})
        return result["messages"][-1].content or ""
    except Exception as e:
        logger.error("completion error: %s", e)
        return f"请求失败：{str(e)}"


def completion_stream(query: str, history: list[dict] | None = None):
    try:
        messages = _build_messages(history or [], query)
        for chunk, metadata in _get_agent().stream(
            {"messages": messages},
            stream_mode="messages",
        ):
            if not isinstance(chunk, AIMessageChunk):
                continue
            if chunk.tool_calls or chunk.tool_call_chunks:
                continue
            content = chunk.content
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b)
                    for b in content
                )
            if content:
                yield content
    except Exception as e:
        logger.error("completion_stream error: %s", e)
        yield f"请求失败：{str(e)}"