from typing import Annotated, Any, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class DPDKDiagnosisState(TypedDict, total=False):
    """
    DPDK 统一诊断状态（支持 realtime_monitor + fault_analysis）

    设计目标：
    - 分层清晰（数据 / 特征 / 检测 / 决策 / 输出）
    - 去重字段
    - 支持 Graph 路由
    """

    # 输入层（外部输入）
    client_id: str
    pid: str
    timestamp: int

    # 数据层（原始数据）
    client_info: dict[str, Any]
    dpdk_info: dict[str, Any]

    metrics_1s: list[dict[str, Any]]
    metrics_5s: list[dict[str, Any]]

    # fault 模式专用
    escalate_result: dict
    core_info: dict[str, Any]

    #  特征层（Feature Engineering）
    log_feature: dict[str, Any]  # 当前窗口特征
    reference_feature: dict[str, Any]  # baseline特征（长期统计）

    #  检测层（Detection）
    rule_flags: list[str]
    semantic_flags: list[str]

    # 汇总异常
    anomaly_flags: list[str]

    # 决策层（Risk & Routing）
    severity: Literal["critical", "warning", "info"]

    should_alert: bool
    escalate_to_fault: bool

    alert_input: dict[str, Any]

    # 控制语义检测是否执行（性能优化）
    allow_semantic: bool

    #  分析层（Fault Analysis 专用）
    description: str
    retrieved_cases: list[dict[str, Any]]

    root_cause: str
    confidence: Literal["high", "medium", "low"]

    call_chain: list[str]

    #  输出层
    alert: dict[str, Any]

    repair_steps: list[str]
    md_report: str
    json_report: dict[str, Any]

    #  LangGraph 消息（自动累积）
    messages: Annotated[list[BaseMessage], add_messages]

    #  控制层（Graph Routing）
    mode: Literal["realtime_monitor", "fault_analysis"]
    next_node: str

    #  可观测性 / Debug
    prompt_meta: dict[str, Any]
    error: str
    run_id: str
