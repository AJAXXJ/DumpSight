# DumpSight

DumpSight 是一个用于监控和分析 DPDK 应用程序崩溃的工具。它能够实时监控 DPDK 应用程序的运行状态，自动捕获核心转储（core dump）文件，并提供基于大语言模型的智能崩溃分析和日志管理功能。

项目采用客户端-服务器（C/S）架构，基于 Flask Web 框架和 SQLAlchemy ORM，集成 Redis 进行监控数据管理，支持使用大语言模型进行智能分析。Agent 模块采用 LangChain 框架，通过图结构（Graph）实现复杂的分析流程。

## 功能特性

### 客户端功能
- **实时监控**：监控 DPDK 应用程序的运行状态，自动检测进程崩溃
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
- **数据存储**：集成 MySQL（SQLAlchemy ORM）和 Redis 进行数据持久化
- **RESTful API**：基于 Flask 提供 RESTful API 接口
- **Agent 智能分析**：基于 LangChain 的图结构（Graph）实现复杂的分析流程
- **案例库管理**：支持历史案例的存储和检索
- **智能报告生成**：自动生成结构化的故障分析报告
- **告警规则配置**：支持自定义告警规则，实时触发告警通知
- **仪表板数据展示**：提供 Web 仪表板，展示客户端状态、核心转储分析结果等

## 项目结构

```
DumpSight/
├── config.py                # 客户端配置管理
├── config.yaml              # 客户端配置文件
├── dumpsight.py            # 客户端主程序入口
├── main.py                 # 服务器启动入口
├── run.sh                  # 运行脚本
├── server-config.yaml      # 服务器配置文件
├── test.py                 # 测试脚本
├── monitor/                # 监控模块
│   ├── daemon.py          # 守护进程管理
│   ├── events.py          # 事件监控和清理任务
│   ├── live_monitor.py    # 实时监控 DPDK 应用状态
│   ├── monitor_manager.py # 监控管理器（RedisMonitorManager）
│   ├── request.py         # 客户端注册和心跳请求
│   ├── coredump_extractor/ # 核心转储提取器
│   │   ├── main.py        # 主入口
│   │   ├── analyzer.py    # GDB 核心转储分析器
│   │   ├── utils.py       # 工具函数
│   │   ├── tools/         # 分析工具
│   │   │   ├── mismatch_pattern.py
│   │   │   └── parse_call_chain.py
│   │   └── extractor/     # 解析器模块
│   │       ├── context_parser.py
│   │       └── meta_parser.py
│   └── dpdk_tools/        # DPDK 工具集
│       ├── cpu_layout.py
│       ├── dpdk_devbind.py
│       ├── dpdk_devbind_helper.py
│       ├── dpdk_hugepages.py
│       └── dpdk_telemetry.py
├── server/                 # 服务器模块
│   ├── app.py             # Flask 应用工厂
│   ├── controller/        # 控制器层
│   │   ├── client_controller.py
│   │   └── dashborad_controller.py
│   ├── service/           # 业务逻辑层
│   │   ├── client_service.py
│   │   ├── dashborad_service.py
│   │   └── alert_service.py
│   ├── repository/        # 数据访问层
│   │   ├── client_repository.py
│   │   ├── client_redis.py
│   │   ├── core_repositiry.py
│   │   └── case_repository.py
│   ├── models/            # 数据模型层
│   │   ├── base_model.py
│   │   └── client/
│   │       ├── client_info.py
│   │       ├── core_info.py
│   │       └── case_info.py
│   ├── tools/             # 服务器工具模块
│   │   ├── api_response.py
│   │   └── metrics_timeseries_collector.py
│   └── __init__.py
├── agent/                  # Agent 智能分析模块
│   ├── main.py            # Agent 主程序
│   ├── live_monitor.py    # Agent 实时监控主程序
│   ├── config/            # Agent 配置
│   │   ├── agent-config.yaml
│   │   ├── llm_factory.py
│   │   ├── settings.py
│   │   ├── alert_rules.py
│   │   └── alert_rules.yaml
│   ├── graphs/            # 分析图
│   │   ├── state.py
│   │   ├── fault_analysis/ # 故障分析图
│   │   │   ├── graph.py
│   │   │   ├── nodes.py
│   │   │   └── edges.py
│   │   └── live_monitor/  # 实时监控图
│   │       ├── graph.py
│   │       ├── nodes.py
│   │       └── edges.py
│   ├── case_library/      # 案例库
│   │   ├── fetcher.py
│   │   ├── rag.py
│   │   ├── tools.py
│   │   └── knowledge/
│   │       ├── faiss_store.py
│   │       ├── data/
│   │       │   ├── library.json
│   │       │   └── faiss_index/
│   │       │       ├── index.faiss
│   │       │       └── index.pkl
│   │       └── template/
│   │           ├── case_template.j2
│   │           └── query_template.j2
│   ├── output/            # 输出处理
│   │   ├── llm_output_formatter.py
│   │   └── report_formatter.py
│   ├── tools/             # Agent 工具集
│   │   ├── fetch_data_tool.py
│   │   ├── telemetry_feature_tool.py
│   │   └── tool_registry.py
│   └── prompts/           # 提示词管理
│       ├── prompt_builder.py
│       ├── prompt_registry.py
│       └── versions/
│           └── v1/
│               ├── few_shots/
│               │   ├── crash_examples.yaml
│               │   └── repair_examples.yaml
│               ├── system/
│               │   ├── case_builder.md
│               │   ├── core_fault_analyst.md
│               │   ├── escalation_fault_analyst.md
│               │   └── realtime_monitor.md
│               └── templates/
│                   ├── alert_generation.j2
│                   ├── anomaly_detection.j2
│                   ├── case_ingestion.j2
│                   ├── core_fault_analysis.j2
│                   ├── escalation_fault_analysis.j2
│                   └── repair_suggestion.j2
├── tools/                 # 通用工具模块
│   ├── common_utils.py
│   ├── constant.py
│   ├── encrypt_decrypt.py
│   ├── logger.py
│   ├── mysql_util.py
│   └── redis_util.py
└── readme.md              # 项目文档
```

## 安装要求

### 客户端
- Python 3.6+
- Linux 系统（需要 root 权限）
- systemd（用于服务管理）
- DPDK 环境（用于 DPDK 应用监控）

### 服务器
- Python 3.6+
- MySQL 数据库
- Redis 缓存
- LLM API（可选，用于智能分析）
- LangChain（用于 Agent 智能分析）

## 依赖安装

### 客户端依赖

```bash
pip install click requests schedule inotify-simple pyinstaller redis pyyaml
```

### 服务器依赖

```bash
pip install flask pyyaml langchain langchain-openai langgraph faiss-cpu openai redis pymysql sqlalchemy
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

编辑 `server-config.yaml` 文件，配置以下参数：

```yaml
# 服务器配置
DEBUG: true
PORT: 5000
SECRET_KEY: "your-secret-key"

# LLM 配置
LLM_MODEL: "your-model-name"
LLM_TEMPERATURE: 0.7
LLM_API_KEY: "your-api-key"
LLM_BASE_URL: "https://api.example.com"

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
```

#### 2. 启动服务器

```bash
python main.py
```

服务器将在 `http://localhost:5000` 启动。

#### 3. API 接口

服务器提供以下 API 接口：

- `POST /api/client/register` - 客户端注册（API 框架已实现，业务逻辑待完善）
- `POST /api/client/heartbeat` - 客户端心跳（API 框架已实现，业务逻辑待完善）
- `GET /api/client/status?client_id=<id>` - 查询客户端状态（API 框架已实现，业务逻辑待完善）
- `POST /api/client/report_crash` - 核心转储分析（API 框架已实现，业务逻辑部分实现）
- `POST /api/agent/fault_analysis` - 故障分析（基于 Agent 图结构）
- `POST /api/agent/live_monitor` - 实时监控分析（基于 Agent 图结构）

## 项目架构

DumpSight 采用客户端-服务器（C/S）架构，基于 Flask Web 框架和 SQLAlchemy ORM，包含以下组件：

### 客户端（Agent）
- **监控模块**：实时监控 DPDK 应用程序状态，捕获核心转储文件
- **监控管理器**：RedisMonitorManager 集成 Redis 进行监控数据管理
- **DPDK 工具集**：提供 CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集等功能
- **守护进程**：以后台方式持续运行，执行定时任务（心跳发送、日志清理等）
- **系统服务**：集成 systemd，支持系统启动自动运行

### 服务器（Server）
- **Flask Web 框架**：提供 RESTful API 接口
- **控制器层**：处理客户端请求，包括注册、心跳、状态查询、核心转储分析（client_controller.py）
- **服务层**：业务逻辑处理（client_service.py 部分实现）
- **数据访问层**：
  - MySQL（SQLAlchemy ORM）数据持久化（client_repository.py 已实现）
  - Redis 数据访问（client_redis.py 已实现，支持 DPDK 信息、核心转储、日志查询）
- **数据模型层**：基于 SQLAlchemy ORM 的数据模型定义（BaseModel、ClientInfo、CoreInfo）
- **LLM Agent**：集成大语言模型进行智能分析（基础框架已实现）
  - LangChain 工具集（tools.py 已实现，包含客户端信息、DPDK 信息、核心转储、日志查询工具）
  - Agent 图结构（graphs/）：基于 LangChain Graph 实现复杂的分析流程
    - 故障分析图（fault_analysis/）：分析崩溃根因、调用链、修复建议
    - 实时监控图（live_monitor/）：实时监控和分析应用状态
  - 案例库（case_library/）：支持历史案例的存储和检索
  - 提示词管理（prompts/）：管理 LLM 分析的提示词模板
  - 输出处理（output/）：处理分析结果的格式化和分发

### 数据流

```
客户端 (Agent)                    服务器 (Server)
       |                                  |
       |  1. 客户端注册                    |
       |--------------------------------->|
       |                                  |
       |  2. 定时心跳                      |
       |--------------------------------->|
       |                                  |
       |  3. 核心转储分析请求              |
       |--------------------------------->|
       |                                  |
       |  4. LLM 智能分析                  |
       |<---------------------------------|
       |  5. 故障分析图处理                |
       |<---------------------------------|
       |  6. 案例库检索                   |
       |<---------------------------------|
       |  7. 生成分析报告                  |
       |<---------------------------------|
```

## 配置说明

### 客户端配置

客户端配置文件位于 `config.yaml`，主要配置项包括：

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

服务器配置文件位于 `server-config.yaml`，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEBUG` | `true` | 调试模式 |
| `PORT` | `5000` | 服务器端口 |
| `SECRET_KEY` | `""` | 服务器密钥（用于客户端密钥验证） |
| `LLM_MODEL` | `""` | LLM 模型名称 |
| `LLM_TEMPERATURE` | `0.7` | LLM 温度参数 |
| `LLM_API_KEY` | `""` | LLM API 密钥 |
| `LLM_BASE_URL` | `""` | LLM API 地址 |
| `MYSQL_HOST` | `localhost` | MySQL 服务器地址 |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_USER` | `root` | MySQL 用户名 |
| `MYSQL_PASSWORD` | `""` | MySQL 密码 |
| `MYSQL_DATABASE` | `DPDK-SERVER` | MySQL 数据库名 |
| `REDIS_HOST` | `localhost` | Redis 服务器地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_DB` | `0` | Redis 数据库编号 |

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

项目包含一个 `run.sh` 脚本，可以快速执行常用操作：

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
1. **数据库依赖**：需要提前安装并配置 MySQL 和 Redis
2. **LLM 配置**：如需使用智能分析功能，需要配置有效的 LLM API
3. **端口占用**：确保配置的端口（默认 5000）未被占用
4. **数据持久化**：MySQL 工具已实现，repository 层已实现（client_repository.py），模型层已实现（BaseModel、ClientInfo）
5. **SQLAlchemy**：服务器使用 SQLAlchemy ORM 进行 MySQL 数据库操作，支持自动创建表结构
6. **密钥配置**：需要配置 SECRET_KEY 用于客户端密钥验证
7. **API 接口**：API 框架已实现，但业务逻辑层（client_service.py）仍需完善
8. **Agent 模块**：需要配置 LLM API 和案例库才能使用完整的智能分析功能

## 开发状态

当前项目处于开发阶段，核心功能已基本实现，部分功能仍在完善中：

### 已完成功能
- **客户端监控功能**：DPDK 应用监控、核心转储捕获、心跳机制、日志管理、守护进程、定期清理
- **核心转储提取器**：支持 GDB 分析、上下文解析、元数据解析、调用链解析
- **核心转储提取器工具**：支持不匹配模式检测和调用链解析（mismatch_pattern.py, parse_call_chain.py）
- **DPDK 工具集**：CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集
- **系统服务集成**：systemd 服务管理，支持开机自启动
- **服务器基础框架**：Flask Web 框架、MySQL 工具（SQLAlchemy ORM）、Redis 工具
- **数据模型层**：BaseModel 基类、ClientInfo 客户端信息模型、CoreInfo 核心转储分析结果模型、CaseInfo 案例模型
- **数据访问层**：
  - MySQL 数据访问（client_repository.py）支持客户端信息的增删改查和分页查询
  - Redis 数据访问（client_redis.py）支持 DPDK 信息、核心转储、日志查询
  - 案例库数据访问（case_repository.py）支持案例存储和检索
- **服务层**：
  - 客户端注册、心跳、状态查询、核心转储分析服务已实现（client_service.py）
  - 密钥验证逻辑已实现
- **Agent 智能分析模块**：
  - 故障分析图（fault_analysis/）：基于 LangChain Graph 实现崩溃分析流程
  - 实时监控图（live_monitor/）：基于 LangChain Graph 实现实时监控分析
  - **Agent实时监控主程序**：独立的实时监控 Agent 入口（live_monitor.py）
  - 案例库（case_library/）：支持历史案例的存储和检索（FAISS 向量存储）
  - 提示词管理（prompts/）：管理 LLM 分析的提示词模板
  - 输出处理（output/）：处理分析结果的格式化和分发
  - 工具集（tools/）：提供客户端信息、DPDK 信息、核心转储、日志查询工具
  - **Agent配置管理**：支持 agent-config.yaml 配置文件和告警规则配置
- **API 接口**：客户端注册、心跳、状态查询、核心转储分析、故障分析、实时监控等接口框架已实现
- **仪表板服务**：提供客户端状态、核心转储分析结果、时间序列指标等数据的展示（部分实现）
- **告警规则配置**：支持自定义告警规则，实时触发告警通知（规则配置已实现，通知机制待完善）
- **时间序列指标收集**：实时收集和存储 DPDK 应用的性能指标（如吞吐量、错误率等）

### 待完善功能
- **仪表板 Web 界面**：完整的 Web 管理界面待开发
- **告警通知渠道**：告警通知的发送渠道（如邮件、Slack）待实现
- **LLM 智能分析深度优化**：分析逻辑和准确性有待进一步提升
- **Agent 技能模块**：扩展更多分析技能和自动化修复能力
- **性能优化**：大规模客户端并发监控的性能优化
- **文档完善**：API 文档和用户使用指南待补充

## 许可证

请根据项目实际情况添加许可证信息。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

请根据项目实际情况添加联系方式。
