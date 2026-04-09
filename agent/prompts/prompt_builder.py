import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from jinja2 import Environment, StrictUndefined, TemplateError
from langchain_core.messages import HumanMessage, SystemMessage
from agent.prompts.prompt_registry import PromptRegistry, get_registry

logger = logging.getLogger(__name__)


# 渲染元数据（用于日志追踪与 A/B 评估）
@dataclass
class PromptMeta:
    """记录一次 prompt 渲染的关键信息，便于与诊断结果关联分析。"""

    template_key: str
    system_key: str
    version: str | None
    rendered_at: float = field(default_factory=time.time)
    content_hash: str = ""  # sha256[:16]，方便去重
    few_shot_count: int = 0
    token_estimate: int = 0  # 粗估 token 数（chars / 4）

    def as_log_dict(self):
        return {
            "template": self.template_key,
            "system": self.system_key,
            "version": self.version or "current",
            "hash": self.content_hash,
            "few_shots": self.few_shot_count,
            "token_est": self.token_estimate,
            "rendered_at": self.rendered_at,
        }


class PromptBuilder:
    """
    将模板 + 系统 prompt + few-shot 组装为最终消息列表。

    设计原则：
    - 每个 build_* 方法对应架构中的一个 Graph 节点。
    - 变量传递使用显式关键字参数，禁止传入 **kwargs 大字典，
      保证模板与调用方之间的契约清晰可检查。
    - Jinja2 使用 StrictUndefined，模板变量缺失立即报错，
      而不是静默渲染为空字符串。
    """

    def __init__(
        self,
        registry=None,
        *,
        include_few_shots=True,
        max_few_shots=3,
    ):
        self._registry = (
            registry or get_registry()
        )  # PromptRegistry 对象，用于获取模板和 few-shot 示例
        self._include_few_shots = include_few_shots  # 是否启用 few-shot 示例
        self._max_few_shots = max_few_shots  # few-shot 示例数量上限
        self._jinja_env = Environment(  # Jinja2 渲染环境
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # 故障分析 Graph 节点：root_cause_reasoning
    def build_fault_analysis(
        self,
        *,
        client_info,
        dpdk_info,
        crash_stack,
        similar_cases,
        extra_context,
    ):
        """
        构建故障根因分析 prompt。

        Returns:
            (messages, meta) — messages 可直接传入 LLM.invoke()
        """
        variables = {
            "client_info": client_info,
            "dpdk_info": dpdk_info,
            "crash_stack": crash_stack,
            "similar_cases": similar_cases,
            "extra_context": extra_context,
            "few_shots": self._get_few_shots("crash_examples"),
        }
        return self._build(
            template_key="fault_analysis",
            system_key="fault_analyst",
            variables=variables,
        )

    # 故障分析 Graph 节点：repair_suggestion
    def build_repair_suggestion(
        self,
        *,
        root_cause,
        dpdk_version,
        crash_context,
    ):
        variables = {
            "root_cause": root_cause,
            "dpdk_version": dpdk_version,
            "crash_context": crash_context,
            "few_shots": self._get_few_shots("repair_examples"),
        }
        return self._build(
            template_key="repair_suggestion",
            system_key="fault_analyst",
            variables=variables,
        )

    # 实时预警 Graph 节点：anomaly_detection
    def build_anomaly_detection(
        self,
        *,
        metrics_1s,
        metrics_5s,
        baseline,
        alert_rules,
    ):
        variables = {
            "metrics_1s": metrics_1s,
            "metrics_5s": metrics_5s,
            "baseline": baseline,
            "alert_rules": alert_rules,
            "few_shots": self._get_few_shots("anomaly_examples"),
        }
        return self._build(
            template_key="anomaly_detection",
            system_key="realtime_monitor",
            variables=variables,
        )

    # 实时预警 Graph 节点：alert_generation
    def build_alert_generation(
        self,
        *,
        anomaly_summary,
        severity,  # "critical" | "warning" | "info"
        client_id,
        metrics_snapshot,
    ):
        if severity not in {"critical", "warning", "info"}:
            raise ValueError(
                f"Invalid severity: '{severity}'. Must be critical/warning/info."
            )
        variables = {
            "anomaly_summary": anomaly_summary,
            "severity": severity,
            "client_id": client_id,
            "metrics_snapshot": metrics_snapshot,
            "few_shots": [],  # 告警生成不使用 few-shot
        }
        return self._build(
            template_key="alert_generation",
            system_key="realtime_monitor",
            variables=variables,
        )

    # 案例库摄取节点：case_ingestion
    def build_case_ingestion(
        self,
        *,
        raw_crash_log,
        core_analysis,
        client_meta,
    ):
        variables = {
            "raw_crash_log": raw_crash_log,
            "core_analysis": core_analysis,
            "client_meta": client_meta,
            "few_shots": [],
        }
        return self._build(
            template_key="case_ingestion",
            system_key="case_builder",
            variables=variables,
        )

    def _build(
        self,
        *,
        template_key,
        system_key,
        variables,
    ):

        system_text = self._registry.get_system(system_key)
        template_src = self._registry.get_template(template_key)

        try:
            human_text = self._render(template_src, variables)
        except TemplateError as exc:
            logger.error(
                "Template render failed | template=%s error=%s",
                template_key,
                exc,
            )
            raise

        messages: list[SystemMessage | HumanMessage] = [
            SystemMessage(content=system_text),
            HumanMessage(content=human_text),
        ]

        meta = self._make_meta(
            template_key=template_key,
            system_key=system_key,
            human_text=human_text,
            few_shot_count=len(variables.get("few_shots", [])),
        )
        logger.info("Prompt built | %s", meta.as_log_dict())
        return messages, meta

    def _render(self, template_src: str, variables: dict[str, Any]) -> str:
        template = self._jinja_env.from_string(template_src)
        return template.render(**variables).strip()

    def _get_few_shots(self, key: str) -> list[dict[str, Any]]:
        if not self._include_few_shots:
            return []
        shots = self._registry.get_few_shots(key)
        return shots[: self._max_few_shots]

    @staticmethod
    def _make_meta(
        *,
        template_key,
        system_key,
        human_text,
        few_shot_count,
    ):
        digest = hashlib.sha256(human_text.encode()).hexdigest()[:16]
        meta = PromptMeta(
            template_key=template_key,
            system_key=system_key,
            version=None,
            content_hash=digest,
            few_shot_count=few_shot_count,
            token_estimate=len(human_text) // 4,
        )
        return meta
