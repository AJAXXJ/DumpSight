import re
import json
from pydantic import ValidationError
from pydantic import BaseModel, Field
from typing import List, Literal
from langchain_core.output_parsers import StrOutputParser
import logging
from typing import TypeVar, Type, Callable, Optional

from pydantic import BaseModel, ValidationError
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FAULT_SCHEMA_PROMPT = """
{
  "root_cause": "string",
  "call_chain": ["string"],
  "confidence": "high | medium | low",
  "repair_steps": ["string"]
}
"""


class FaultAnalysisResult(BaseModel):

    root_cause: str = Field(..., description="根本原因")

    call_chain: List[str] = Field(default_factory=list, description="调用链或触发路径")

    confidence: Literal["high", "medium", "low"] = Field(..., description="置信度")

    repair_steps: List[str] = Field(default_factory=list, description="修复步骤")


REPAIR_SCHEMA_PROMPT = """
{
  "repair_steps": ["string"]
}
"""


class RepairSteps(BaseModel):

    repair_steps: List[str] = Field(default_factory=list, description="修复步骤")



def extract_json_str(raw: str) -> str:
    """
    从 LLM 原始输出中提取 JSON 字符串。
    按优先级依次尝试：
      1. 剥离 ```json ... ``` / ``` ... ``` 代码块
      2. 直接匹配最外层 { ... }
      3. 无法提取则原样返回，交由下游报错
    """
    # 剥离各种 fence（```json、```JSON、``` 均兼容）
    fence_match = re.search(
        r"```(?:json)?\s*\n?([\s\S]*?)\n?```",
        raw,
        re.IGNORECASE,
    )
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.startswith("{") or candidate.startswith("["):
            return candidate

    # 回退：贪婪匹配最外层花括号
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        return brace_match.group(0)

    return raw.strip()


class JsonParseError(Exception):
    """JSON 提取或解析失败"""

class SchemaValidationError(Exception):
    """Pydantic schema 校验失败"""


def parse_with_schema(raw: str, schema: Type[T]) -> T:
    """
    将字符串解析为 Pydantic schema 实例。
    抛出细化异常，便于上层针对性处理。
    """
    json_str = extract_json_str(raw)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise JsonParseError(f"JSON 解析失败: {e}\n原始内容片段: {json_str[:200]}") from e

    try:
        return schema(**data)
    except ValidationError as e:
        raise SchemaValidationError(f"Schema 校验失败: {e}") from e


_REPAIR_PROMPT_TMPL = """
请修复以下 JSON，使其严格符合给定 schema，要求：
- 只输出合法 JSON，不要输出任何额外文本或 markdown
- 所有必填字段必须存在且类型正确

Schema 说明：
{schema_desc}

待修复 JSON：
{broken_json}
""".strip()


def output_json_parse(
    llm_output: str,
    schema: Type[T],
    schema_desc: str,
    llm_retry_fn: Optional[Callable[[str], str]] = None,
    max_retries: int = 2,
) -> T:
    """
    将 LLM 输出解析为 schema 实例，失败时自动调用 LLM 修复并重试。

    Args:
        llm_output:    LLM 原始输出字符串
        schema:        目标 Pydantic 模型类
        schema_desc:   schema 的自然语言描述，注入修复 prompt
        llm_retry_fn:  接受 prompt str、返回 str 的重试函数；
                       为 None 时不重试，直接抛出异常
        max_retries:   最大重试次数（默认 2）

    Returns:
        校验通过的 schema 实例

    Raises:
        JsonParseError | SchemaValidationError: 所有重试耗尽后仍失败
    """
    current_output = llm_output
    last_error: Exception = JsonParseError("未执行任何解析")

    # 首次解析 + 最多 max_retries 次修复重试
    for attempt in range(max_retries + 1):
        try:
            return parse_with_schema(current_output, schema)

        except (JsonParseError, SchemaValidationError) as e:
            last_error = e

            if attempt == 0:
                logger.warning("首次解析失败: %s", e)
            else:
                logger.warning("第 %d 次修复后仍失败: %s", attempt, e)

            # 无重试函数或已达上限 → 终止
            if llm_retry_fn is None or attempt >= max_retries:
                break

            # 调用 LLM 修复
            repair_prompt = _REPAIR_PROMPT_TMPL.format(
                schema_desc=schema_desc,
                broken_json=current_output,
            )
            logger.info("调用 LLM 修复 JSON，第 %d 次尝试...", attempt + 1)

            try:
                raw_response = llm_retry_fn(repair_prompt)
                current_output = (
                    StrOutputParser().invoke(raw_response)
                    if not isinstance(raw_response, str)
                    else raw_response
                )
            except Exception as retry_err:
                logger.error("LLM 修复调用本身失败: %s", retry_err)
                break

    raise last_error