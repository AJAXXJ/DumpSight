# 🧩 coredump_extractor

`coredump_extractor` 是 **DumpSight** 中用于 **Core 崩溃现场提取** 的基础模块。

---

## 🚀 核心能力

* 📥 接收输入：

  * `core` 文件（必选）
  * 可执行文件 `exe`（可选）
  * 应用日志 `log`（可选）

* ⚙️ 自动分析：

  * 调用 `gdb` 执行批处理命令
  * 提取崩溃线程、调用栈、寄存器、内存映射等关键信息

* 🖥️ 采集环境：

  * `/proc` 进程信息
  * HugePage / CPU / NUMA
  * 网卡绑定状态（DPDK）
  * 应用日志尾部

* 📦 输出标准化结果：

  * `*.meta.json` 👉 **发生了什么**
  * `*.context.json` 👉 **当时环境如何**

---

## 📁 目录结构

```
coredump_extractor/
├── main.py
├── analyzer.py
├── extractor/
│   ├── meta_parser.py
│   └── context_parser.py
├── constant.py
└── utils.py
```

### 🔹 main.py

* 对外入口：`run_core_extractor`
* 输入校验与识别
* 文件稳定性检测
* 调度分析流程并输出 JSON

### 🔹 analyzer.py

核心调度模块：

* `analyze_core()` → 解析 GDB 输出，构建 `meta`
* `collect_context()` → 采集环境，构建 `context`
* `analyze_core_dump()` → 返回 `(meta, context)`

### 🔹 extractor/meta_parser.py

负责 **GDB 输出解析**：

* 信号 & 崩溃类型
* 调用栈（backtrace）
* 线程信息
* 寄存器
* 共享库
* DPDK 子系统识别

### 🔹 extractor/context_parser.py

负责 **运行环境采集**：

* `/proc/<pid>` 快照
* HugePage / 内存
* `lscpu`
* `dpdk-devbind.py`
* 日志尾部分析

### 🔹 constant.py

* 信号映射
* 空闲线程规则
* 关键寄存器
* DPDK 库列表
* 超时配置

### 🔹 utils.py

* `safe_run`：安全执行命令
* `safe_read_text`：安全读取文件
* `wait_file_stable`：文件稳定检测
* `is_probable_executable`：可执行文件判断

---

## 🔄 工作流程（End-to-End）

### 1️⃣ 输入识别

`resolve_input_files`

* 必须：1 个 `core.*`
* 可选：

  * 0~1 个 `.log`
  * 0~1 个可执行文件
* ❌ 不允许未知文件

---

### 2️⃣ 文件稳定性检测

`wait_file_stable`

* 条件：

  * 连续两次大小一致
  * 且 > 0
* 超时仅告警，不中断

---

### 3️⃣ GDB 批量采集

`parse_core`

执行：

```
gdb --batch --quiet
```

采集内容：

* `info threads`
* `thread apply all bt 5`
* `bt full`
* `info registers`
* `x/4xg $rsp / $rbp`
* `info shared`
* `show args`
* `info proc mappings`

---

### 4️⃣ 崩溃信息解析（meta）

`parse_gdb_output` + `analyze_core`

生成：

* 崩溃信号 & 类型
* 崩溃帧 & 调用栈
* 线程信息
* 寄存器
* 共享库

#### 🔍 符号可信度评估

```text
symbol_status:
  - ok
  - mismatch
  - partial
  - unknown
```

依据：

* `gdb` 返回码
* stderr 信息
* build-id 匹配情况

---

### 5️⃣ 运行环境采集（context）

`parse_gdb_context`

特点：

👉 **单项失败不影响整体**

---

### 6️⃣ 输出结果

```
<core>.meta.json
<core>.context.json
```

---

## 📥 输入约束

```python
run_core_extractor(input_paths, output_dir)
```

必须满足：

* ✅ 仅 1 个 `core.*`
* ✅ ≤1 个 `.log`
* ✅ ≤1 个可执行文件
* ❌ 不允许未知文件

---

### 🧠 文件名智能解析

若 core 文件符合：

```
core.<exe>.<pid>.<tid>.<signal>.<timestamp>.<encoded_path>
```

将自动提取：

* PID / TID
* Signal
* 原始可执行路径

---

## 📤 输出说明

### 🧾 meta.json（崩溃事实）

**核心字段：**

* 基本信息：

  * `core_file`, `exe_name`, `exe_path`
  * `pid`, `tid`, `signal`, `timestamp`

* GDB 信息：

  * `returncode`, `stderr`
  * `symbol_status`, `symbol_warnings`

* 解析结果：

  * `crash_frame`
  * `backtrace`
  * `threads`
  * `registers`
  * `shared_libs`
  * `dpdk_subsystems`
  * `crash_address_type`

---

### 🖥️ context.json（运行环境）

**核心字段：**

* `/proc`：

  * `cmdline`, `maps`, `status`, `limits`

* 内存：

  * `hugepages_2M`, `hugepages_1G`
  * `meminfo`

* CPU：

  * `lscpu`

* 网络：

  * `nic_status`

* 日志：

  * `app_log_tail`
  * `app_log_parsed`

* 错误记录：

  * `errors`

---

## 💡 使用示例

```python
from monitor.core_extrator.coredump_extractor.main import run_core_extractor

result = run_core_extractor(
    input_paths=[
        "/path/to/core.xxx",
        "/path/to/app_binary",  # 可选
        "/path/to/app.log",     # 可选
    ],
    output_dir="/path/to/output",
)

print(result["meta_file"])
print(result["context_file"])
```

---
