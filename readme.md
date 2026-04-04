# DumpSight

DumpSight 是一个用于监控和分析 DPDK 应用程序崩溃的工具。它能够实时监控 DPDK 应用程序的运行状态，自动捕获核心转储（core dump）文件，并提供崩溃分析和日志管理功能。

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

### 服务器功能
- **客户端管理**：支持客户端注册、状态查询和心跳接收
- **核心转储分析**：提供核心转储文件分析接口
- **LLM 集成**：支持使用大语言模型进行智能分析
- **数据存储**：集成 MySQL 和 Redis 进行数据持久化

## 项目结构

```
DPDK/
├── config.py                # 客户端配置管理
├── config.yaml              # 客户端配置文件
├── dumpsight.py             # 客户端主程序入口
├── main.ipynb               # Jupyter 笔记本
├── run.sh                   # 运行脚本
├── monitor/                 # 监控模块
│   ├── constant.py          # 信号常量映射
│   ├── live_monitor.py      # 实时监控 DPDK 应用状态
│   ├── monitor_utils.py     # 监控工具函数
│   ├── request.py           # 客户端注册和心跳请求
│   └── dpdk_tools/          # DPDK 工具集
│       ├── cpu_layout.py            # CPU 布局分析
│       ├── dpdk_devbind.py         # DPDK 设备绑定工具
│       ├── dpdk_devbind_helper.py  # 设备绑定辅助工具
│       ├── dpdk_hugepages.py       # HugePage 状态查询
│       └── dpdk_telemetry.py       # DPDK 遥测数据采集
├── tools/                   # 工具模块
│   ├── daemon.py            # 守护进程和 systemd 服务管理
│   ├── events.py            # 事件监控和清理任务
│   ├── logger.py            # 日志配置
│   ├── redis_util.py        # Redis 工具
│   └── utils.py             # 工具函数
├── server/                  # 服务器模块
│   ├── main.py              # 服务器主程序（Flask 应用）
│   ├── config.yaml          # 服务器配置文件
│   ├── agent/               # Agent 模块
│   │   └── agent_client.py  # LLM Agent 客户端
│   ├── controller/          # 控制器层
│   │   └── client_controller.py  # 客户端相关 API
│   ├── repository/          # 数据访问层（待实现）
│   ├── service/             # 业务逻辑层（待实现）
│   └── tools/               # 服务器工具
│       ├── mysql_util.py    # MySQL 工具（待实现）
│       └── redis_util.py    # Redis 工具
└── readme.md                # 项目文档
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

## 依赖安装

### 客户端依赖

```bash
pip install click requests schedule inotify-simple pyinstaller
```

### 服务器依赖

```bash
pip install flask pyyaml langchain-openai redis pymysql
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

编辑 `server/config.yaml` 文件，配置以下参数：

```yaml
# 服务器配置
DEBUG: true
PORT: 5000

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
cd server
python main.py
```

服务器将在 `http://localhost:5000` 启动。

#### 3. API 接口

服务器提供以下 API 接口：

- `POST /api/client/register` - 客户端注册
- `POST /api/client/heartbeat` - 客户端心跳
- `GET /api/client/status?client_id=<id>` - 查询客户端状态
- `POST /api/client/core_analyse` - 核心转储分析

## 项目架构

DumpSight 采用客户端-服务器（C/S）架构，包含以下组件：

### 客户端（Agent）
- **监控模块**：实时监控 DPDK 应用程序状态，捕获核心转储文件
- **DPDK 工具集**：提供 CPU 布局分析、HugePage 状态查询、设备绑定状态检查、遥测数据采集等功能
- **守护进程**：以后台方式持续运行，执行定时任务（心跳发送、日志清理等）
- **系统服务**：集成 systemd，支持系统启动自动运行

### 服务器（Server）
- **Flask Web 框架**：提供 RESTful API 接口
- **控制器层**：处理客户端请求，包括注册、心跳、状态查询、核心转储分析
- **服务层**：业务逻辑处理（待实现）
- **数据访问层**：MySQL 和 Redis 数据持久化（待实现）
- **LLM Agent**：集成大语言模型进行智能分析

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

服务器配置文件位于 `server/config.yaml`，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEBUG` | `true` | 调试模式 |
| `PORT` | `5000` | 服务器端口 |
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
- `<encoded_path>`: 编码的可执行文件路径

## 信号映射

支持的信号类型：

| 信号编号 | 信号名称 | 说明 |
|----------|----------|------|
| 6 | SIGABRT | 进程中止 |
| 11 | SIGSEGV | 段错误 |
| 8 | SIGFPE | 浮点异常 |
| 4 | SIGILL | 非法指令 |

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

### 服务器
1. **数据库依赖**：需要提前安装并配置 MySQL 和 Redis
2. **LLM 配置**：如需使用智能分析功能，需要配置有效的 LLM API
3. **端口占用**：确保配置的端口（默认 5000）未被占用
4. **数据持久化**：repository 和 service 层待实现，当前 API 接口仅返回模拟数据

## 待实现功能

### 客户端
- [x] 客户端注册功能
- [x] 核心转储捕获
- [x] 心跳机制
- [x] 守护进程管理
- [ ] 崩溃告警通知机制

### 服务器
- [x] 客户端注册接口
- [x] 心跳接收接口
- [x] 客户端状态查询接口
- [x] 核心转储分析接口
- [ ] 客户端注册数据持久化（MySQL）
- [ ] 心跳数据持久化（MySQL）
- [ ] 核心转储分析逻辑实现
- [ ] LLM 智能分析集成
- [ ] Web 管理界面
- [ ] 告警通知机制

## 许可证

请根据项目实际情况添加许可证信息。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

请根据项目实际情况添加联系方式。

