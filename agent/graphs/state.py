from typing import Annotated, Any, Literal
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AlertPayload(TypedDict, total=False):
    alert_id: str
    severity: Literal["critical", "warning", "info"]
    title: str
    description: str
    client_id: str
    triggered_at: float


class PromptMeta(TypedDict, total=False):
    template: str
    system: str
    version: str | None
    hash: str
    few_shots: int
    token_est: int


class DPDKDiagnosisState(TypedDict, total=False):
    """
    两个 Graph 共享的完整状态。
    total=False 表示所有字段均可选，节点按需填写。

    字段分组：
      [输入]      原始数据，由入口节点从 Tools 拉取后写入
      [中间]      各分析节点的计算结果，逐步填充
      [输出]      最终交付内容
      [控制]      Graph 路由与流程控制
      [追踪]      日志与可观测性
    """

    # 外部输入
    client_id: str
    pid: str
    timestamp: int

    # 拉取数据
    client_info: dict[str, Any]  # 客户端信息
    dpdk_info: dict[str, Any]  # dpdk 实例信息
    core_info: dict[str, Any]  # crash core 信息
    metrics_1s: dict[str, Any]  # 1s 周期指标快照
    metrics_5s: dict[str, Any]  # 5s 周期聚合指标
    baseline: dict[str, Any]

    # 中间
    description: str  # 案例描述用于向量库检索
    retrieved_cases: list[dict[str, Any]]  # 案例库检索结果
    anomaly_flags: list[str]  # 触发的异常标志列表
    root_cause: str  # LLM 输出的根因判断
    confidence: Literal["high", "medium", "low"]
    call_chain: list[str]  # 从堆栈还原的关键调用帧
    alert_rules: list[AlertPayload]

    # 输出
    repair_steps: list[str]  # 修复建议（有序列表）
    md_report: str  # 最终故障报告（Markdown）
    json_report: dict  # 最终故障报告（json）
    alert: AlertPayload  # 实时预警负载

    # LangChain 消息历史 add_messages 自动追加不覆盖
    messages: Annotated[list[BaseMessage], add_messages]

    # 控制
    mode: Literal["fault_analysis", "realtime_monitor"]
    next_node: str  # 条件边用于动态路由
    should_alert: bool  # 预警 Graph：是否触发告警
    escalate_to_fault: bool  # 预警 Graph：是否升级为故障分析

    # 追踪
    prompt_meta: PromptMeta  # 本轮渲染的 prompt 元数据
    error: str  # 节点异常信息（非空则路由到错误处理）
    run_id: str  # 每次调用的唯一 ID（UUID）
