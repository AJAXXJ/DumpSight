# DumpSight

DumpSight 是一个用于监控和分析 DPDK 应用程序崩溃的工具。它能够实时监控 DPDK 应用程序的运行状态，自动捕获核心转储（core dump）文件，并提供崩溃分析和日志管理功能。

## 功能特性

- **实时监控**：监控 DPDK 应用程序的运行状态，自动检测进程崩溃
- **核心转储捕获**：自动配置系统核心转储模式，捕获崩溃时的核心转储文件
- **日志管理**：自动记录应用程序的运行日志，便于问题排查
- **守护进程**：以后台守护进程方式运行，持续监控系统状态
- **定期清理**：自动清理过期的核心转储文件和日志文件
- **心跳机制**：支持向服务器发送心跳，报告客户端存活状态
- **Systemd 集成**：支持 systemd 服务管理，方便系统启动和重启

## 项目结构

```
DPDK/
├── agent/
│   └── main.py              # Agent 主程序（待实现）
├── monitor/
│   ├── constant.py          # 信号常量映射
│   ├── monitor_utils.py     # 监控工具函数
│   └── request.py           # 客户端注册和心跳请求
├── tools/
│   ├── daemon.py            # 守护进程和 systemd 服务管理
│   ├── events.py            # 事件监控和清理任务
│   ├── logger.py            # 日志配置
│   └── utils.py             # 工具函数
├── config.py                # 配置管理
├── dumpsight.py             # 主程序入口
├── main.ipynb               # Jupyter 笔记本
├── run.sh                   # 运行脚本
└── readme.md                # 项目文档
```

## 安装要求

- Python 3.6+
- Linux 系统（需要 root 权限）
- systemd（用于服务管理）

## 依赖安装

```bash
pip install click requests schedule inotify-simple pyinstaller
```

## 快速开始

### 1. 初始化设置

使用 `setup` 命令初始化 DumpSight 环境：

```bash
sudo python dumpsight.py setup
```

该命令会：
- 配置系统核心转储模式
- 安装并启动 systemd 服务

### 2. 监控 DPDK 应用

使用 `monitor` 命令监控 DPDK 应用程序：

```bash
sudo python dumpsight.py monitor /path/to/dpdk_app --no-huge -m 64 --vdev net_null0
```

选项：
- `--log`: 指定日志文件名（默认自动生成唯一 ID）

### 3. 查看状态

使用 `status` 命令查看 DumpSight 状态：

```bash
sudo python dumpsight.py status
```

### 4. 守护进程管理

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

## 配置说明

配置文件位于 `config.py`，主要配置项包括：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `server_url` | `http://localhost:8000` | 服务器地址 |
| `heartbeat_interval` | `60` | 心跳间隔（秒） |
| `schedule_clean_crashed_core_interval` | `600` | 清理崩溃核心转储的间隔（秒） |
| `monitor_file` | `monitor-dpdk.json` | 监控信息文件 |
| `tmp_dir` | `tmp` | 临时目录 |
| `logs_dir` | `tmp/logs` | 日志目录 |
| `core_dump_dir` | `tmp/core_dumps` | 核心转储目录 |

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

1. **Root 权限**：大部分命令需要 root 权限才能正常运行
2. **核心转储配置**：确保系统核心转储功能已启用
3. **磁盘空间**：核心转储文件可能占用较大磁盘空间，建议定期清理
4. **日志管理**：日志文件会持续增长，建议配置日志轮转

## 待实现功能

- [ ] 客户端注册功能
- [ ] 核心转储分析模块
- [ ] Web 管理界面
- [ ] 告警通知机制

## 许可证

请根据项目实际情况添加许可证信息。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

请根据项目实际情况添加联系方式。

