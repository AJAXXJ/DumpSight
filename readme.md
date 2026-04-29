# DumpSight

DumpSight 是一个用于监控和分析 DPDK 应用程序崩溃的工具。它能够实时监控 DPDK 应用程序的运行状态，自动捕获核心转储（core dump）文件，并提供基于大语言模型的智能崩溃分析和日志管理功能。

项目采用客户端-服务器（C/S）架构，基于 Flask Web 框架，集成 Redis / MySQL / PostgreSQL（PGVector）/ Elasticsearch / MinIO 等多种数据存储，支持使用大语言模型进行智能分析。Agent 模块采用 LangChain + LangGraph 框架，通过图结构（Graph）实现复杂的分析流程。

## 功能特性

### 客户端功能
- **实时监控**：监控 DPDK 应用程序的运行状态，自动检测进程崩溃
- **DPDKLiveMonitor**：多 DPDK 实例并发 Telemetry 遥测数据采集（1s 高频+5s 低频双频轮询），设备绑定一致性检查
- **核心转储捕获**：自动配置系统核心转储模式，捕获崩溃时的核心转储文件
- **日志管理**：自动记录应用程序的运行日志，便于问题排查
- **守护进程**：以后台守护进程方式运行，持续监控系统状态
- **定期清理**：自动清理过期的核心转储文件和日志文件
- **心跳机制**：支持向服务器发送心跳，报告客户端存活状态
- **Systemd 集成**：支持 systemd 服务管理，方便系统启动和重启
- **DPDK 工具集**：提供 CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集等功能
- **Redis 监控管理器**：集成 RedisMonitorManager 进行监控数据管理
- **核心转储提取器**：集成 CoredumpExtractor 进行核心转储文件解析和分析

### 服务器功能
- **客户端管理**：支持客户端注册、状态查询和心跳接收
- **核心转储分析**：提供核心转储文件分析接口
- **LLM 集成**：支持使用大语言模型进行智能分析，包括故障分析和实时监控
- **Agent 实时监控（Live Monitor）**：双频轮询策略（规则引擎 10s + LLM 语义兜底 60s），LangGraph 图驱动，自动注册/注销监控实例
- **数据存储**：集成 MySQL（SQLAlchemy ORM）、Redis、PostgreSQL（PGVector）、Elasticsearch 进行数据持久化与检索
- **MinIO 对象存储**：集成 MinIO 进行知识文档的存储和管理
- **RESTful API**：基于 Flask 提供 RESTful API 接口
- **Agent 智能分析**：基于 LangChain + LangGraph 的图结构（Graph）实现复杂的分析流程
- **案例库管理**：支持历史案例的 FAISS 向量检索 + ES 全文检索的混合存储与检索
- **智能报告生成**：自动生成结构化的故障分析报告
- **告警规则配置**：支持自定义告警规则，实时触发告警通知
- **邮件通知系统**：支持 SMTP 邮件发送崩溃告警和反馈邮件
- **交互式对话**：支持基于 LLM Agent 的智能问答与交互
- **知识库管理**：支持文档上传、分块、向量化存储与语义检索（基于 PGVector）
- **仪表板数据展示**：提供 Web 仪表板，展示客户端状态、核心转储分析结果、时序指标等

### 前端功能
- **客户端信息查看**：查看已注册客户端的详细信息，包括状态、配置和运行指标
- **实例信息查看**：查看每个客户端的 DPDK 实例信息，包括进程 ID、CPU 绑定、HugePage 使用情况等
- **运行实例监控**：实时监控 DPDK 实例的运行状态，包括 CPU 使用率、内存使用率、网络吞吐量等指标
- **崩溃报告展示**：展示核心转储分析报告，包括崩溃原因、调用链、寄存器状态和修复建议
- **调用链展示**：可视化展示崩溃时的函数调用链，帮助定位问题根源
- **异常时序图展示**：通过时序图展示异常事件的发生顺序和关联关系，辅助故障分析
- **崩溃调用图可视化**：基于图数据结构展示多线程调用链关系

## 项目结构

```
DumpSight/
├── config.py                    # 客户端配置管理
├── dumpsight.py                 # 客户端主程序入口（CLI）
├── main.py                      # 服务器启动入口
├── run.sh                       # 运行脚本
├── server-config.yaml           # 服务器配置文件
├── test.py                      # 测试脚本
├── monitor/                     # 监控模块
│   ├── daemon.py               # 守护进程管理
│   ├── events.py               # 事件监控和清理任务
│   ├── live_monitor.py         # 实时监控 DPDK 应用状态（DPDKLiveMonitor）
│   ├── monitor_manager.py      # 监控管理器（RedisMonitorManager）
│   ├── request.py              # 客户端注册和心跳请求
│   ├── coredump_extractor/     # 核心转储提取器
│   │   ├── main.py             # 主入口
│   │   ├── analyzer.py         # GDB 核心转储分析器
│   │   ├── utils.py            # 工具函数
│   │   ├── tools/              # 分析工具
│   │   │   ├── mismatch_pattern.py    # 不匹配模式检测
│   │   │   └── parse_call_chain.py    # 调用链解析
│   │   └── extractor/          # 解析器模块
│   │       ├── context_parser.py      # 上下文解析器
│   │       └── meta_parser.py         # 元数据解析器
│   └── dpdk_tools/             # DPDK 工具集
│       ├── cpu_layout.py
│       ├── dpdk_devbind.py
│       ├── dpdk_devbind_helper.py
│       ├── dpdk_hugepages.py
│       └── dpdk_telemetry.py
├── server/                      # 服务器模块
│   ├── app.py                  # Flask 应用工厂
│   ├── controller/             # 控制器层
│   │   ├── client_controller.py      # 客户端管理接口
│   │   ├── dashboard_controller.py   # 仪表板数据接口
│   │   ├── knowledge_controller.py   # 知识库管理接口
│   │   ├── case_controller.py        # 案例管理接口
│   │   ├── alert_controller.py       # 告警/邮件配置接口
│   │   └── chat_controller.py        # 交互式对话接口
│   ├── service/                # 业务逻辑层
│   │   ├── client_service.py
│   │   ├── dashboard_service.py
│   │   ├── alert_service.py
│   │   ├── case_service.py
│   │   ├── chat_service.py
│   │   └── knowledge_service.py
│   ├── repository/             # 数据访问层
│   │   ├── client_repository.py      # MySQL 客户端数据访问
│   │   ├── client_redis.py           # Redis 数据访问
│   │   ├── core_repository.py        # 核心转储数据访问
│   │   ├── case_repository.py        # 案例数据访问
│   │   ├── alert_repository.py       # 告警/邮件数据访问
│   │   └── knowledge_repository.py   # 知识库数据访问
│   ├── models/                 # 数据模型层
│   │   ├── base_model.py             # SQLAlchemy 基类
│   │   ├── knowledge_info.py         # 知识文档信息模型
│   │   ├── client/                   # 客户端相关模型
│   │   │   ├── client_info.py
│   │   │   ├── core_info.py
│   │   │   └── case_info.py
│   │   └── email/                    # 邮件相关模型
│   │       ├── smtp_config.py
│   │       ├── alert_rule.py
│   │       ├── alert_rule_recipient.py
│   │       └── alert_mail_log.py
│   ├── notification/           # 邮件通知模块
│   │   ├── email_sender.py          # SMTP 邮件发送器
│   │   ├── mail_builder.py          # 邮件内容构建
│   │   ├── crash_mail.py            # 崩溃告警邮件
│   │   ├── feedback_mail.py         # 反馈邮件
│   │   ├── test_crash_email.py      # 邮件测试脚本
│   │   └── test.py
│   └── tools/                  # 服务器工具模块
│       ├── api_response.py
│       ├── exception_handler.py     # 全局异常处理
│       └── metrics_timeseries_collector.py
├── agent/                       # Agent 智能分析模块
│   ├── main.py                 # Agent 主程序（故障分析/监控轮询入口）
│   ├── live_monitor.py         # Agent 实时监控管理（双频轮询/注册/同步）
│   ├── client/                 # LLM 客户端
│   │   ├── llm_client.py       # LLM Agent 客户端（含工具调用）
│   │   └── tools/              # Agent 工具集
│   │       ├── __init__.py
│   │       ├── case_search.py       # 案例检索工具
│   │       ├── client_info.py       # 客户端信息查询
│   │       ├── client_list.py       # 客户端列表查询
│   │       ├── dpdk_info.py         # DPDK 实例信息查询
│   │       ├── dpdk_list.py         # DPDK 实例列表查询
│   │       └── log_info.py          # 日志查询工具
│   ├── config/                 # Agent 配置
│   │   ├── agent-config.yaml
│   │   ├── llm_factory.py      # LLM 实例工厂
│   │   ├── settings.py         # 配置加载
│   │   ├── alert_rules.py      # 告警规则定义（dataclass）
│   │   └── alert_rules.yaml    # 告警规则配置（YAML）
│   ├── graphs/                 # 分析图（LangGraph）
│   │   ├── state.py            # 统一诊断状态（DPDKDiagnosisState）
│   │   ├── fault_analysis/     # 故障分析图
│   │   │   ├── graph.py
│   │   │   ├── nodes.py
│   │   │   └── edges.py
│   │   └── live_monitor/       # 实时监控图
│   │       ├── graph.py
│   │       ├── nodes.py
│   │       └── edges.py
│   ├── case_library/           # 案例库（RAG）
│   │   ├── fetcher.py          # 案例获取
│   │   ├── retrieve.py         # 案例检索（FAISS + ES 混合检索）
│   │   ├── render.py           # 模板渲染
│   │   └── store/              # 存储后端
│   │       ├── faiss_store.py      # FAISS 向量存储
│   │       ├── es_store.py         # Elasticsearch 全文检索存储
│   │       ├── data/               # 数据文件
│   │       │   ├── dpdk_crash_cases.json
│   │       │   ├── library.json
│   │       │   └── faiss_index/
│   │       │       ├── index.faiss
│   │       │       └── index.pkl
│   │       └── template/           # 模板文件
│   │           ├── case_template.j2
│   │           └── query_template.j2
│   ├── knowledge/              # 知识库模块
│   │   ├── chunking.py         # 文档解析与分块（PDF/DOCX/TXT）
│   │   └── embedding.py        # 向量化处理
│   ├── output/                 # 输出处理
│   │   ├── llm_output_formatter.py  # LLM 输出格式化
│   │   └── report_formatter.py      # 报告格式化
│   ├── tools/                  # Agent 分析工具集
│   │   ├── tool_registry.py         # 工具注册
│   │   ├── fetch_data_tool.py       # 数据获取工具
│   │   ├── telemetry_feature_tool.py # 遥测特征提取与基线构建
│   │   └── call_chain_tool.py       # 调用链图构建与可视化
│   └── prompts/                # 提示词管理
│       ├── prompt_builder.py
│       ├── prompt_registry.py
│       └── versions/
│           └── v1/
│               ├── few_shots/       # Few-shot 示例
│               │   ├── crash_examples.yaml
│               │   └── repair_examples.yaml
│               ├── system/          # 系统提示词
│               │   ├── case_builder.md
│               │   ├── core_fault_analyst.md
│               │   ├── escalation_fault_analyst.md
│               │   └── realtime_monitor.md
│               └── templates/       # 分析模板
│                   ├── alert_generation.j2
│                   ├── anomaly_detection.j2
│                   ├── case_ingestion.j2
│                   ├── core_fault_analysis.j2
│                   ├── escalation_fault_analysis.j2
│                   └── repair_suggestion.j2
└── tools/                      # 通用工具模块
    ├── common_utils.py         # 通用工具函数
    ├── constant.py             # 常量定义
    ├── encrypt_decrypt.py      # 加密解密
    ├── logger.py               # 日志配置
    ├── mysql_util.py           # MySQL 连接工具（SQLAlchemy）
    ├── redis_util.py           # Redis 连接工具
    ├── es_util.py              # Elasticsearch 连接工具
    ├── minio_util.py           # MinIO 对象存储工具
    ├── pgvector_util.py        # PGVector 向量数据库工具
    └── vector_store_util.py    # 向量存储统一封装（PGVector 实现）
```

## 安装要求

### 客户端
- Python 3.8+
- Linux 系统（需要 root 权限）
- systemd（用于服务管理）
- DPDK 环境（用于 DPDK 应用监控）

### 服务器
- Python 3.8+
- MySQL 5.7+ 数据库
- Redis 缓存
- PostgreSQL 14+（含 pgvector 插件，用于知识库向量存储，可选）
- Elasticsearch 7+（用于案例库全文检索，可选）
- MinIO 对象存储（用于知识文档管理，可选）
- LLM API（可选，用于智能分析）
- LangChain + LangGraph（用于 Agent 智能分析）

## 依赖安装

### 客户端依赖

```bash
pip install click requests schedule inotify-simple pyinstaller redis pyyaml
```

### 服务器依赖

```bash
pip install flask flask-cors pyyaml langchain langchain-openai langgraph \
            openai redis pymysql sqlalchemy \
            elasticsearch minio psycopg2-binary pgvector \
            pdfplumber python-docx beautifulsoup4 pytesseract \
            jinja2
```

## 快速开始

### 客户端使用

#### 1. 初始化设置

使用 `setup` 命令初始化 DumpSight 环境：

```bash
sudo python dumpsight.py setup --client_id <your_client_id> --server_url <server_url>
```

该命令会：
- 配置客户端 ID 和服务器地址
- 向服务器注册客户端
- 配置系统核心转储模式
- 安装并启动 systemd 服务

#### 2. 监控 DPDK 应用

使用 `monitor` 命令监控 DPDK 应用程序：

```bash
sudo python dumpsight.py monitor /path/to/dpdk_app --no-huge -m 64 --vdev net_null0
```

选项：
- `--log`: 指定日志文件名（默认自动生成唯一 ID）

#### 3. 查看状态

使用 `status` 命令查看 DumpSight 状态：

```bash
sudo python dumpsight.py status
```

#### 4. 守护进程管理

```bash
# 启动守护进程
sudo python dumpsight.py daemon_start

# 停止守护进程
sudo python dumpsight.py daemon_stop

# 重启守护进程
sudo python dumpsight.py daemon_restart

# 直接运行守护进程（前台）
sudo python dumpsight.py daemon
```

### 服务器使用

#### 1. 配置服务器

编辑 [`server-config.yaml`](server-config.yaml) 文件，根据实际环境配置以下参数：

```yaml
# 服务器配置
DEBUG: true
PORT: 5000
SECRET_KEY: "your-secret-key"

# MySQL 配置
MYSQL_HOST: "localhost"
MYSQL_PORT: 3306
MYSQL_USER: "root"
MYSQL_PASSWORD: "your-password"
MYSQL_DATABASE: "DPDK-SERVER"

# Redis 配置
REDIS_HOST: "localhost"
REDIS_PORT: 6379
REDIS_DB: 0

# Agent 参数
FAST_INTERVAL: 10
SLOW_INTERVAL: 60
SYNC_INTERVAL: 30
VECTOR_DIM: 1024

# MinIO 对象存储（可选，用于知识库文档管理）
MINIO:
  HOST: "localhost:9000"
  ACCESS_KEY: "admin"
  SECRET_KEY: "your-secret-key"
  BUCKET_NAME: "dpdk-knowledge"

# PGVector 向量数据库（可选，用于知识库向量检索）
PYVECTOR:
  HOST: "localhost"
  PORT: 5432
  DBNAME: "dpdk_knowledge"
  USER: "postgres"
  PASSWORD: "your-password"

# Elasticsearch（可选，用于案例库全文检索）
ELASTICSEARCH:
  HOST: "http://localhost:9200"
  USER: null
  PASSWORD: null
```

#### 2. 启动服务器

```bash
python main.py
```

服务器将在 `http://localhost:5000` 启动。

#### 3. Agent 配置

编辑 [`agent/config/agent-config.yaml`](agent/config/agent-config.yaml) 配置 LLM、向量存储、检索、监控等参数：

```yaml
llm:
  fast_model: qwen3.5-flash      # 快速模型（规则检测/语义检测）
  strong_model: qwen3.6-plus     # 强模型（用于深度故障分析）
  temperature: 0.0
  max_tokens: 4096
  timeout: 60                    # LLM 调用超时（秒）
  max_retries: 3                 # LLM 调用重试次数

api_keys:
  openai_api_key: "sk-xxxx"
  openai_api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"

vector_store:
  type: chroma                    # 向量存储类型
  chroma:
    host: localhost
    port: 8000
    collection: dpdk_cases

embedding:
  model: text-embedding-v4        # 嵌入模型

metadata_db:
  url: sqlite:///./case_library.db  # 案例元数据库

retriever:
  top_k: 5                        # 检索 Top-K
  score_threshold: 0.7            # 检索分数阈值

monitor:
  interval_1s: 1.0               # 高频轮询间隔（秒）
  interval_5s: 5.0               # 低频轮询间隔（秒）
  webhook_url: ""                # Webhook 告警地址
  cooldown_sec: 60               # 告警冷却时间（秒）

prompt:
  version: "v1"                   # 提示词版本
  few_shots_enabled: true
  few_shots_max: 3

langgraph:
  checkpointer_type: memory       # 检查点类型（memory / sqlite）
  checkpointer_db_url: ./langgraph_checkpoints.db

log:
  level: INFO                     # 日志级别
  json: false                     # 是否输出 JSON 格式日志

elasticsearch:
  host: "http://localhost:9200"
  user: null
  password: null
  index: "dumpsight_cases"
```

## API 接口

### 客户端管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/client/register` | 客户端注册 |
| POST | `/api/client/heartbeat` | 客户端心跳 |
| GET | `/api/client/status?client_id=<id>` | 查询客户端状态 |
| POST | `/api/client/report_crash` | 核心转储分析上报 |

### 仪表板

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dpdk/dashboard/client-list` | 获取所有客户端列表 |
| GET | `/dpdk/dashboard/client-info?client_id=<id>` | 获取客户端详细信息 |
| GET | `/dpdk/dashboard/core-list?client_id=<id>` | 获取核心转储列表 |
| GET | `/dpdk/dashboard/core-info?core_id=<id>` | 获取核心转储详细信息 |
| GET | `/dpdk/dashboard/running-instances?client_id=<id>` | 获取运行实例信息 |
| GET | `/dpdk/dashboard/timeseries` | 获取时序指标数据 |
| GET | `/dpdk/dashboard/case-page` | 分页查询案例 |
| GET | `/dpdk/dashboard/crash-call-graph` | 获取崩溃调用图数据 |
| GET | `/dpdk/dashboard/crash-timeline` | 获取崩溃时序数据 |

### 知识库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/dpdk/knowledge/upload` | 获取 MinIO 上传签名 |
| POST | `/dpdk/knowledge/minio/event` | MinIO 事件回调（自动触发解析与向量化） |
| DELETE | `/dpdk/knowledge/delete` | 删除知识文档 |
| GET | `/dpdk/knowledge/page` | 分页查询知识文档列表 |
| POST | `/dpdk/knowledge/search` | 语义搜索知识文档 |

### 案例管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/dpdk/case/insert` | 新增案例 |
| GET | `/dpdk/case/get/<case_id>` | 获取案例详情 |
| POST | `/dpdk/case/update` | 更新案例 |
| DELETE | `/dpdk/case/delete/<case_id>` | 删除案例 |
| GET | `/dpdk/case/page` | 分页查询案例 |
| GET | `/dpdk/case/search` | 全文搜索案例（ES） |

### 智能对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/dpdk/chat` | 智能问答（LLM Agent，带工具调用） |
| POST | `/dpdk/chat/stream` | 流式智能问答（SSE 格式） |

### 告警与邮件配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dpdk/alert/smtp-config` | 获取 SMTP 配置 |
| POST | `/dpdk/alert/smtp-config` | 保存 SMTP 配置 |
| POST | `/dpdk/alert/test-connection` | 测试 SMTP 连接 |
| GET | `/dpdk/alert/mail-logs` | 获取邮件发送日志 |
| GET | `/dpdk/alert/rules` | 获取告警规则列表 |

### Agent 分析接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/fault_analysis` | 故障分析（基于 Agent 图结构） |
| POST | `/api/agent/live_monitor` | 实时监控分析（基于 Agent 图结构） |

## 实时监控系统（Live Monitor）

DumpSight 的实时监控系统采用**客户端-服务器双层架构**，将数据采集与智能分析解耦：

### 第一层：客户端实时监控（DPDK 遥测数据采集）

客户端通过 [`monitor/live_monitor.py`](monitor/live_monitor.py) 的 [`DPDKLiveMonitor`](monitor/live_monitor.py:223) 类实现多实例并发监控：

- **多实例管理**：支持通过 [`add_instance()`](monitor/live_monitor.py:324) / [`remove_instance()`](monitor/live_monitor.py:352) 动态增删被监控的 DPDK 进程实例
- **双频轮询（1s/5s）**：
  - **高频轮询（1s）**：[`poll_1s()`](monitor/live_monitor.py:81) — 采集 `/ethdev/stats`、`/mempool/info`、`/dmadev/stats` 等实时吞吐与错误指标
  - **低频轮询（5s）**：[`poll_5s()`](monitor/live_monitor.py:130) — 采集 `/ethdev/xstats`、`/eal/lcore/usage`、`/eal/heap_info` 等深度统计
- **环境感知**：[`environment()`](monitor/live_monitor.py:18) 自动采集 DPDK 版本、CPU 拓扑、HugePage 状态、设备绑定状态
- **存活检测**：[`is_dpdk_alive()`](monitor/live_monitor.py:69) 通过 telemetry socket 检测进程存活
- **设备一致性检查**：[`check_devbind_on_anomaly()`](monitor/live_monitor.py:193) 检测网卡是否异常脱离 DPDK 驱动
- **线程安全 Buffer**：每实例独立采集线程，结果写入线程安全 buffer，由外部统一 [`flush()`](monitor/live_monitor.py:255)

### 第二层：服务端 Agent 实时监控（智能预警）

服务端通过 [`agent/live_monitor.py`](agent/live_monitor.py) 实现面向多客户端的双频智能监控管理：

#### 双频监控策略

每个 DPDK 实例启动两条监控线程，通过 LangGraph 图驱动：

| 维度 | 快速轮询（Fast Poll） | 慢速轮询（Slow Poll） |
|------|----------------------|----------------------|
| **间隔** | `fast_interval`（默认 10s） | `slow_interval`（默认 60s） |
| **语义检测** | ❌ 不触发 LLM | ✅ 规则无异常时触发 LLM 兜底 |
| **延迟** | 秒级 | 分钟级 |
| **覆盖场景** | 确定性异常（阈值越界） | 规则盲区（联动劣化、趋势异常） |

#### 线程管理

- **注册**：[`register_client_monitor()`](agent/live_monitor.py:126) — 为客户端启动双频监控线程（防重复注册）
- **注销**：[`unregister_client_monitor()`](agent/live_monitor.py:162) — 停止线程并清理冷却缓存
- **同步**：[`sync_client_monitors()`](agent/live_monitor.py:199) — 定时对比数据库 running 实例与注册表，自动注册新实例、注销已停止实例
- **全局关闭**：[`unregister_all_monitors()`](agent/live_monitor.py:184) — 服务关闭时统一清理

#### LangGraph 实时监控图

[`agent/graphs/live_monitor/`](agent/graphs/live_monitor/) 定义了 7 个节点组成的图拓扑：

```
START → fetch_metrics
          ├─(error)───────────────────────────→ handle_error → END
          └─(ok)──→ rule_detection
                        ├─(error)─────────────→ handle_error → END
                        ├─(规则有异常)─────────→ risk_assessment
                        ├─(规则无异常+快速轮询)→ END
                        └─(规则无异常+慢速轮询)→ semantic_detection
                                                    ├─(error)────→ handle_error → END
                                                    ├─(语义有异常)→ risk_assessment
                                                    └─(无异常)───→ END
                                                          ↓
                                                  risk_assessment
                                                    ├─(escalate)─→ escalate_to_fault → END
                                                    ├─(alert)────→ alert_generation → END
                                                    └─(冷却/无需)→ END
```

| 节点 | 功能 |
|------|------|
| [`fetch_metrics`](agent/graphs/live_monitor/nodes.py:80) | 从 Redis 拉取最近 10s 的 1s/5s 日志，构建 log_feature 和 reference_feature（5min TTL 缓存基线） |
| [`rule_detection`](agent/graphs/live_monitor/nodes.py:147) | 遍历告警规则引擎（确定性阈值 + 参考值对比），规则级冷却期内过滤重复告警 |
| [`semantic_detection`](agent/graphs/live_monitor/nodes.py:175) | LLM 语义分析，捕捉规则无法覆盖的多指标联动劣化、趋势异常，失败时静默降级 |
| [`risk_assessment`](agent/graphs/live_monitor/nodes.py:212) | 合并 rule_flags + semantic_flags，计算最高 severity，severity 级全局冷却兜底，决策告警或升级 |
| [`alert_generation`](agent/graphs/live_monitor/nodes.py:270) | LLM 生成人类可读告警标题和描述，失败时降级为结构化模板文本（含关键指标） |
| [`escalate_to_fault`](agent/graphs/live_monitor/nodes.py:316) | 切换至故障分析模式，拉取 core dump 数据进行深度分析 |
| [`handle_error`](agent/graphs/live_monitor/nodes.py:333) | 记录错误日志并重置告警状态，终止本轮执行 |

#### 告警规则引擎

告警规则定义在 [`agent/config/alert_rules.yaml`](agent/config/alert_rules.yaml)，通过 [`AlertRule`](agent/config/alert_rules.py:8) dataclass 加载：

| 属性 | 说明 |
|------|------|
| `id` | 规则唯一标识 |
| `metric` | 监控指标名（对应 log_feature 的 _FEATURE_PATH_MAP 键，如 `rx_pps`、`rx_errors`、`mempool_free` 等） |
| `condition` | 条件类型：`gt` / `lt` / `gte` / `lte` / `eq` / `ref_ratio` / `ref_delta` |
| `threshold` | 阈值 |
| `severity` | 等级：`critical` / `warning` / `info` |
| `cooldown_sec` | 规则级冷却时间（秒） |
| `escalate_to_fault` | 是否触发故障升级 |
| `enabled` | 是否启用 |

#### 冷却机制（防告警风暴）

- **规则级冷却**：每条规则触发后进入冷却期（`cooldown_sec`），粒度 `client_id:rule_id`
- **Severity 级全局冷却**：同一 severity 等级的告警全局冷却（`monitor.cooldown_sec`），粒度 `client_id:severity:{level}`
- **多线程安全**：所有冷却读写通过 `_cooldown_lock` 保护，消除 TOCTOU 竞争

#### 状态对象

实时监控使用统一的 [`DPDKDiagnosisState`](agent/graphs/state.py:7) TypedDict，分层清晰：

- **输入层**：`client_id`、`pid`、`timestamp`
- **数据层**：`client_info`、`dpdk_info`、`metrics_1s`、`metrics_5s`
- **特征层**：`log_feature`（当前窗口）、`reference_feature`（基线）
- **检测层**：`rule_flags`、`semantic_flags`、`anomaly_flags`
- **决策层**：`should_alert`、`escalate_to_fault`、`alert_input`
- **输出层**：`alert`（含标题、描述、severity、时间戳）

## 项目架构

DumpSight 采用客户端-服务器（C/S）架构，基于 Flask Web 框架，包含以下组件：

### 客户端（Agent）
- **实时监控（DPDKLiveMonitor）**：[`DPDKLiveMonitor`](monitor/live_monitor.py:223) 类实现多 DPDK 实例并发 Telemetry 数据采集，1s/5s 双频轮询，线程安全 Buffer 上报
- **监控模块**：实时监控 DPDK 应用程序状态，捕获核心转储文件
- **监控管理器**：RedisMonitorManager 集成 Redis 进行监控数据管理
- **DPDK 工具集**：提供 CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集等功能
- **核心转储提取器**：基于 GDB 的核心转储文件解析、调用链分析、上下文提取
- **守护进程**：以后台方式持续运行，执行定时任务（心跳发送、日志清理等）
- **系统服务**：集成 systemd，支持系统启动自动运行

### 服务器（Server）
- **Flask Web 框架**：提供 RESTful API 接口，支持 CORS 跨域
- **控制器层**：处理客户端管理、仪表板、知识库、案例、告警、对话等请求
- **服务层**：业务逻辑处理，涵盖客户端管理、仪表板、告警、案例、对话、知识库等服务
- **数据访问层**：
  - MySQL（SQLAlchemy ORM）：客户端信息、核心转储、案例、告警规则等持久化
  - Redis：DPDK 应用信息、核心转储、日志等监控数据
  - PGVector：知识文档向量存储与语义检索
  - Elasticsearch：案例库全文检索
  - MinIO：知识文档对象存储
- **数据模型层**：基于 SQLAlchemy ORM 的数据模型定义
- **邮件通知系统**：基于 SMTP 的崩溃告警邮件发送，支持多收件人、HTML 模板
- **Agent 实时监控管理（agent/live_monitor.py）**：双频监控线程管理（fast/slow poll）、定时同步注册表、告警/故障升级回调
- **LLM Agent**：集成大语言模型进行智能分析
  - LLM 客户端：支持工具调用的 Agent 封装（client_info、dpdk_info、log_info、case_search 等工具）
  - LangGraph 图结构：故障分析图（fault_analysis/）和实时监控图（live_monitor/）实现复杂分析流程
  - 实时监控图：7 节点图（fetch_metrics → rule_detection → semantic_detection → risk_assessment → alert_generation / escalate_to_fault），支持规则引擎 + LLM 语义检测 + 双层冷却
  - 案例库 RAG：FAISS 向量检索 + Elasticsearch 全文检索的混合检索
  - 知识库管理：文档上传（MinIO）→ 解析分块（PDF/DOCX/TXT）→ 向量化（Embedding）→ 存储（PGVector）
  - 提示词管理：多版本提示词模板和 Few-shot 示例
  - 调用链分析：崩溃调用链图构建与可视化

### 数据流

```
客户端 (Monitor)                     服务器 (Server)
       |                                     |
       |  1. 客户端注册                       |
       |------------------------------------>|
       |                                     |
       |  2. 定时心跳                         |
       |------------------------------------>|
       |                                     |
       |  3. DPDK 遥测数据采集（1s/5s 双频）  |
       |     DPDKLiveMonitor → Redis Buffer   |
       |------------------------------------>|
       |  4. 核心转储分析上报                 |
       |------------------------------------>|
       |                                     |
       |  5. Agent 实时监控双频轮询           |
       |    ├─ Fast Poll (10s): 规则引擎      |
       |    └─ Slow Poll (60s): 规则+LLM语义  |
       |<------------------------------------|
       |  6. 规则/语义检测 → 告警生成         |
       |     或升级为故障分析                  |
       |<------------------------------------|
       |  7. 故障分析（LangGraph）            |
       |<------------------------------------|
       |  8. 案例库检索（FAISS + ES）          |
       |<------------------------------------|
       |  9. 告警规则匹配 & 邮件通知          |
       |<------------------------------------|
       | 10. 生成分析报告                     |
       |<------------------------------------|

                              用户交互
                                  |
                      ┌──────────┴──────────┐
                      │                      │
                  Web 仪表板             LLM 对话
                      │                      │
                      │  客户端/实例/崩溃     │  智能问答/工具调用
                      │  信息展示             │  案例检索/知识检索
                      │  时序指标/调用图      │  流式输出
                      └──────────────────────┘
```

## 配置说明

### 客户端配置

客户端配置文件位于 [`config.py`](config.py)，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `schedule_heartbeat_interval` | `10` | 心跳间隔（秒） |
| `schedule_clean_crashed_core_interval` | `600` | 清理崩溃核心转储的间隔（秒） |
| `monitor_file` | `monitor-dpdk.json` | 监控信息文件 |
| `tmp_dir` | `tmp` | 临时目录 |
| `logs_dir` | `tmp/logs` | 日志目录 |
| `core_dump_dir` | `tmp/core_dumps` | 核心转储目录 |
| `REDIS_HOST` | `localhost` | Redis 服务器地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_DB` | `0` | Redis 数据库编号 |

### 服务器配置

服务器配置文件位于 [`server-config.yaml`](server-config.yaml)，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEBUG` | `true` | 调试模式 |
| `PORT` | `5000` | 服务器端口 |
| `SECRET_KEY` | `""` | 服务器密钥（用于客户端密钥验证） |
| `MYSQL_HOST` | `localhost` | MySQL 服务器地址 |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_USER` | `root` | MySQL 用户名 |
| `MYSQL_PASSWORD` | `""` | MySQL 密码 |
| `MYSQL_DATABASE` | `DPDK-SERVER` | MySQL 数据库名 |
| `REDIS_HOST` | `localhost` | Redis 服务器地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_DB` | `0` | Redis 数据库编号 |
| `FAST_INTERVAL` | `10` | 快速轮询间隔（秒） |
| `SLOW_INTERVAL` | `60` | 慢速轮询间隔（秒） |
| `SYNC_INTERVAL` | `30` | 同步间隔（秒） |
| `VECTOR_DIM` | `1024` | 向量维度 |
| `MINIO.HOST` | - | MinIO 服务地址 |
| `MINIO.ACCESS_KEY` | - | MinIO 访问密钥 |
| `MINIO.SECRET_KEY` | - | MinIO 秘密密钥 |
| `MINIO.BUCKET_NAME` | `dpdk-knowledge` | MinIO 存储桶 |
| `PYVECTOR.HOST` | `localhost` | PGVector 主机 |
| `PYVECTOR.PORT` | `5432` | PGVector 端口 |
| `PYVECTOR.DBNAME` | `dpdk_knowledge` | PGVector 数据库 |
| `PYVECTOR.USER` | `postgres` | PGVector 用户 |
| `PYVECTOR.PASSWORD` | `""` | PGVector 密码 |
| `ELASTICSEARCH.HOST` | - | ES 服务地址 |
| `ELASTICSEARCH.USER` | - | ES 用户名 |
| `ELASTICSEARCH.PASSWORD` | - | ES 密码 |

### Agent 配置

Agent 配置文件位于 [`agent/config/agent-config.yaml`](agent/config/agent-config.yaml)，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `llm.fast_model` | `qwen3.5-flash` | 快速 LLM 模型（用于语义检测/告警生成） |
| `llm.strong_model` | `qwen3.6-plus` | 强 LLM 模型（用于深度故障分析） |
| `llm.temperature` | `0.0` | 生成温度 |
| `llm.max_tokens` | `4096` | 最大 Token 数 |
| `llm.timeout` | `60` | LLM 调用超时（秒） |
| `llm.max_retries` | `3` | LLM 调用重试次数 |
| `api_keys.openai_api_key` | - | LLM API 密钥 |
| `api_keys.openai_api_base` | - | LLM API 地址 |
| `vector_store.type` | `chroma` | 向量存储类型 |
| `vector_store.chroma` | - | Chroma 连接配置（host / port / collection） |
| `embedding.model` | `text-embedding-v4` | 嵌入模型 |
| `metadata_db.url` | `sqlite:///./case_library.db` | 案例元数据库连接 |
| `retriever.top_k` | `5` | 检索 Top-K |
| `retriever.score_threshold` | `0.7` | 检索分数阈值 |
| `monitor.interval_1s` | `1.0` | 客户端高频轮询间隔（秒） |
| `monitor.interval_5s` | `5.0` | 客户端低频轮询间隔（秒） |
| `monitor.webhook_url` | `""` | 告警 Webhook 回调地址 |
| `monitor.cooldown_sec` | `60` | 告警冷却时间（秒，severity 级全局冷却） |
| `prompt.version` | `v1` | 提示词版本 |
| `prompt.few_shots_enabled` | `true` | 是否启用 Few-shot 示例 |
| `prompt.few_shots_max` | `3` | Few-shot 最大示例数 |
| `langgraph.checkpointer_type` | `memory` | LangGraph 检查点类型（memory / sqlite） |
| `langgraph.checkpointer_db_url` | - | LangGraph 检查点数据库路径 |
| `log.level` | `INFO` | 日志级别 |
| `log.json` | `false` | 是否输出 JSON 格式日志 |
| `elasticsearch.host` | - | Elasticsearch 服务地址 |
| `elasticsearch.index` | `dumpsight_cases` | 案例库 ES 索引名 |

### 核心转储提取器配置

核心转储提取器使用 GDB 进行核心转储文件分析，主要功能包括：
- 解析核心转储文件名格式
- 提取线程信息、调用栈、寄存器状态
- 分析崩溃原因和上下文
- 支持日志文件关联分析

支持的信号类型：

| 信号编号 | 信号名称 | 说明 |
|----------|----------|------|
| 6 | SIGABRT | 进程中止 |
| 11 | SIGSEGV | 段错误 |
| 8 | SIGFPE | 浮点异常 |
| 4 | SIGILL | 非法指令 |

## 核心转储文件命名格式

核心转储文件采用以下命名格式：

```
core.<exe>.<pid>.<tid>.<signal>.<timestamp>.<encoded_path>
```

- `<exe>`: 可执行文件名
- `<pid>`: 进程 ID
- `<tid>`: 线程 ID
- `<signal>`: 信号编号
- `<timestamp>`: 时间戳
- `<encoded_path>`: 编码的可执行文件路径（路径中的 `/` 替换为 `!`）

## Redis 数据结构

客户端使用 Redis 存储监控数据，主要数据结构包括：

### DPDK 应用信息
- **Key 格式**: `{client_id}:info:{pid}`
- **数据类型**: JSON
- **存储内容**: DPDK 应用的运行状态信息

### 核心转储信息
- **Key 格式**: `{client_id}:core:{pid}:{timestamp}`
- **数据类型**: JSON
- **存储内容**: 核心转储分析结果

### 日志信息
- **Key 格式**: `{client_id}:log:{pid}:{record_type}:{timestamp}`
- **数据类型**: JSON
- **存储内容**: DPDK 应用日志（record_type 为 "1s" 或 "5s"）

## 打包为可执行文件

使用 PyInstaller 将程序打包为单个可执行文件：

```bash
pyinstaller --onefile dumpsight.py
```

## 运行脚本

项目包含一个 [`run.sh`](run.sh) 脚本，可以快速执行常用操作：

```bash
bash run.sh
```

## 注意事项

### 客户端
1. **Root 权限**：大部分命令需要 root 权限才能正常运行
2. **核心转储配置**：确保系统核心转储功能已启用
3. **磁盘空间**：核心转储文件可能占用较大磁盘空间，建议定期清理
4. **日志管理**：日志文件会持续增长，建议配置日志轮转
5. **DPDK 环境**：监控 DPDK 应用需要确保 DPDK 环境已正确配置
6. **Redis 连接**：客户端需要连接 Redis 服务器进行监控数据管理

### 服务器
1. **数据库依赖**：需要提前安装并配置 MySQL 和 Redis；PGVector / ES / MinIO 为可选依赖
2. **LLM 配置**：如需使用智能分析功能，需要配置有效的 LLM API
3. **端口占用**：确保配置的端口（默认 5000）未被占用
4. **密钥配置**：需要配置 SECRET_KEY 用于客户端密钥验证
5. **Agent 模块**：需要配置 LLM API 和案例库才能使用完整的智能分析功能
6. **知识库功能**：使用知识库需要配置 MinIO 和 PGVector
7. **邮件通知**：使用邮件告警需要配置 SMTP 信息

## 开发状态

当前项目处于持续开发阶段，核心功能已基本实现：

### 已完成功能
- **客户端监控功能**：DPDK 应用监控、核心转储捕获、心跳机制、日志管理、守护进程、定期清理
- **客户端实时监控（DPDKLiveMonitor）**：
  - 多 DPDK 实例并发监控，支持动态增删实例
  - 双频 Telemetry 数据采集（1s 高频吞吐/错误 + 5s 低频深度统计）
  - 环境感知：DPDK 版本、CPU 拓扑、HugePage、设备绑定状态
  - 设备绑定一致性检查（自动检测网卡异常脱离 DPDK 驱动）
  - 线程安全 Buffer 批量上报
- **核心转储提取器**：支持 GDB 分析、上下文解析、元数据解析、调用链解析、不匹配模式检测
- **DPDK 工具集**：CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集
- **系统服务集成**：systemd 服务管理，支持开机自启动
- **服务器基础框架**：Flask Web 框架、CORS 跨域支持
- **数据持久化**：
  - MySQL（SQLAlchemy ORM）数据访问层：客户端信息、核心转储、案例、告警规则
  - Redis 数据访问：DPDK 信息、核心转储、日志查询
  - PGVector 向量存储：知识文档向量检索
  - Elasticsearch 全文检索：案例库全文搜索
  - MinIO 对象存储：知识文档管理
- **数据模型层**：BaseModel、ClientInfo、CoreInfo、CaseInfo、KnowledgeInfo、SMTPConfig、AlertRule、AlertRuleRecipient、AlertMailLog
- **服务层**：
  - 客户端注册、心跳、状态查询、核心转储分析
  - 仪表板数据展示：客户端状态、核心转储、时序指标、调用图
  - 告警规则配置与邮件通知
  - 案例管理（CRUD + 全文检索）
  - 知识库管理（上传 → 解析 → 分块 → 向量化 → 检索）
  - 智能对话（LLM Agent + 工具调用 + 流式输出）
- **全局异常处理**：统一异常拦截与格式化返回
- **Agent 智能分析模块**：
  - LLM Agent 客户端：支持工具调用的 Agent 封装
  - Agent 工具集：client_info、client_list、dpdk_info、dpdk_list、log_info、case_search
  - 故障分析图（fault_analysis/）：基于 LangGraph 的崩溃分析流程
  - 实时监控图（live_monitor/）：基于 LangGraph 的 7 节点实时监控分析图
  - **服务端实时监控管理（agent/live_monitor.py）**：
    - 双频监控策略：快速轮询（规则引擎，10s）+ 慢速轮询（LLM 语义兜底，60s）
    - 监控注册表管理：自动注册新实例、注销已停止实例
    - 定时同步线程：对比数据库 running 实例与注册表，动态增删监控
    - 告警/故障升级回调机制
  - **实时监控（agent/graphs/live_monitor/）**：
    - 数据拉取 → 规则检测 → 语义检测 → 风险评估 → 告警生成 / 故障升级 完整图流程
    - 规则引擎：支持绝对阈值（gt/lt/gte/lte/eq）和参考值对比（ref_ratio/ref_delta）
    - LLM 语义检测：捕获规则盲区的多指标联动劣化和趋势异常
    - 双层冷却机制：规则级冷却 + severity 级全局冷却，防告警风暴
    - reference_feature 基线缓存（5min TTL）
  - 案例库 RAG：FAISS 向量检索 + Elasticsearch 全文检索的混合检索
  - 知识库管理：文档分块（chunking）与向量化（embedding）
  - 提示词管理：多版本提示词模板和 Few-shot 示例
  - 调用链分析：崩溃调用链图构建与可视化
  - Agent 配置管理：agent-config.yaml 配置文件和告警规则配置（YAML 驱动的 AlertRule dataclass）
- **邮件通知系统**：
  - SMTP 邮件发送器（支持 SSL/TLS）
  - 崩溃告警邮件（HTML 模板）
  - 邮件发送日志记录
  - SMTP 配置管理（数据库持久化）
  - 告警规则与收件人管理
- **API 接口**：客户端管理、仪表板、案例管理、知识库管理、智能对话、告警配置等完整接口

### 待完善功能
- **LLM 智能分析深度优化**：分析逻辑和准确性有待进一步提升
- **Agent 技能模块**：扩展更多分析技能和自动化修复能力
- **告警通知渠道扩展**：除邮件外增加 Slack / Webhook 等通知方式
- **大规模客户端并发监控**：性能优化
- **文档完善**：API 文档和用户使用指南待补充

## 许可证

请根据项目实际情况添加许可证信息。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

请根据项目实际情况添加联系方式。
