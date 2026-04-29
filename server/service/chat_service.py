from agent.client.llm_client import completion, completion_stream
from tools.logger import logger

NEWLINE = "\n"
ESCAPED_NEWLINE = "\\n"


def chat(query: str, history: list[dict] | None = None) -> str:
    return completion(query, history)


def chat_stream(query: str, history: list[dict] | None = None):
    total = 0
    try:
        for delta in completion_stream(query, history):
            data = delta.replace(NEWLINE, ESCAPED_NEWLINE)
            total += len(delta)
            yield f"data: {data}\n\n"
        logger.info("chat_stream done, total chars: %d", total)
    except GeneratorExit:
        logger.debug("chat_stream: client disconnected at %d chars", total)
        return
    except Exception as e:
        logger.error("chat_stream error at %d chars: %s", total, e)
        yield f"data: 请求失败：{str(e)}\n\n"
    finally:
        yield "event: done\ndata: \n\n"