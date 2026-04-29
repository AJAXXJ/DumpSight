import os
import re

from tools.constant import APP_LOG_INIT_LINES, KEY_LS_CPU, COLLECT_TIMEOUT, APP_LOG_TAIL_LINES
from monitor.coredump_extractor.utils import safe_run, safe_read_text


_NIC_SECTION_MAP = {
    "network devices using dpdk-compatible driver": "network",
    "network devices using kernel driver":          "network",
    "network devices":                              "network",
    "baseband":                                     "baseband",
    "crypto":                                       "crypto",
    "dma":                                          "dma",
    "eventdev":                                     "eventdev",
    "mempool":                                      "mempool",
    "compress":                                     "compress",
    "misc":                                         "misc",
    "regex":                                        "regex",
    "ml":                                           "ml",
}

_HUGEPAGE_PATHS = {
    "2M": "/sys/kernel/mm/hugepages/hugepages-2048kB",
    "1G": "/sys/kernel/mm/hugepages/hugepages-1048576kB",
}

def extract_proc_info(pid, context):
    """
    提取进程的上下文信息
    """
    if not pid:
        context["proc_snapshot_available"] = False
        context["proc_info"] = "pid unavailable"
        return

    proc_dir = f"/proc/{pid}"
    if not os.path.exists(proc_dir):
        context["proc_snapshot_available"] = False
        context["proc_info"] = f"/proc/{pid} not found"
        return

    context["proc_snapshot_available"] = True
    context["cmdline"] = (safe_read_text(f"{proc_dir}/cmdline") or "").replace("\x00", " ")
    context["maps"] = safe_read_text(f"{proc_dir}/maps") or ""
    context["status"] = safe_read_text(f"{proc_dir}/status") or ""
    context["limits"] = safe_read_text(f"{proc_dir}/limits") or ""


def extract_dpdk_hugepage(context):
    """
    提取 DPDK hugepage 状态
    """    
    hp = {}
    for size, base in _HUGEPAGE_PATHS.items():
        total = safe_read_text(f"{base}/nr_hugepages")
        free  = safe_read_text(f"{base}/free_hugepages")
        if total is not None:
            hp[f"hugepages_{size}"] = {
                "total": (total or "").strip(),
                "free":  (free  or "").strip(),
            }
    if hp:
        context["hugepages"] = hp

    meminfo_text = safe_read_text("/proc/meminfo")
    if meminfo_text:
        context["meminfo"] = {
            parts[0].strip(): parts[1].strip()
            for line in meminfo_text.splitlines()
            if ":" in line
            for parts in [line.split(":", 1)]
            if any(k in parts[0] for k in ["HugePages", "MemFree", "MemAvailable"])
        }


def extract_cpu_topology(context):
    """
    提取 CPU/NUMA 拓扑信息
    """
    r = safe_run(["lscpu"], timeout=COLLECT_TIMEOUT)
    if r.returncode != 0:
        context["lscpu"] = {"info": "lscpu unavailable", "stderr": (r.stderr or "").strip()}
        return

    filtered = {}
    for line in (r.stdout or "").splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            if key in KEY_LS_CPU:
                filtered[key] = val.strip()

    context["lscpu"] = filtered


def parse_nic_status(raw: str) -> dict:
    """
    将 dpdk-devbind.py --status 的原始输出解析为结构化字典。
    
    返回格式：
    {
        "network": [{"pci": "0000:00:05.0", "desc": "Virtio network device 1000",
                     "if": "eth0", "drv": "virtio-pci", "unused": "vfio-pci", "active": True}],
        "baseband": [],
        "crypto": [],
        ...
    }
    """
    result = {v: [] for v in dict.fromkeys(_NIC_SECTION_MAP.values())}

    current = None

    for line in raw.splitlines():
        line = line.strip()
        if not line or re.match(r"^=+$", line):
            continue

        # 匹配段落标题
        lower = line.lower()
        matched_section = next(
            (key for key in _NIC_SECTION_MAP if key in lower), None
        )
        if matched_section:
            current = _NIC_SECTION_MAP[matched_section]
            continue

        # 跳过 "No xxx devices detected"
        if line.lower().startswith("no ") and "detected" in line.lower():
            continue

        # 解析设备行：0000:00:05.0 'desc' if=eth0 drv=xxx unused=yyy *Active*
        if current is None:
            continue

        m = re.match(r"^([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f])\s+'([^']+)'(.*)$", line)
        if not m:
            continue

        pci, desc, rest = m.group(1), m.group(2), m.group(3)
        dev = {
            "pci":    pci,
            "desc":   desc,
            "if":     _kv(rest, "if"),
            "drv":    _kv(rest, "drv"),
            "unused": _kv(rest, "unused"),
            "active": "*Active*" in rest,
        }
        result[current].append(dev)

    return result


def _kv(text: str, key: str) -> str:
    """从 'key=value' 格式的字符串中提取 value，找不到返回空字符串。"""
    m = re.search(rf"{key}=(\S+)", text)
    return m.group(1) if m else ""


def extract_nic_status(context):
    """提取网卡和 PMD 状态"""
    r = safe_run(["dpdk-devbind.py", "--status"], timeout=COLLECT_TIMEOUT)
    if r.returncode != 0:
        context["nic_status"] = {"error": "dpdk-devbind.py unavailable"}
        return

    context["nic_status"] = parse_nic_status(r.stdout)


def _parse_app_log_structured(text: str) -> dict:
    """
    从应用日志头部提取结构化字段（仅原始提取，不做分析）。
    调用方应传入前 APP_LOG_INIT_LINES 行拼接的文本。
    """
    if not text:
        return {}

    patterns = {
        "detected_lcores": (
            r"EAL:\s*Detected CPU lcores:\s*(\d+)",
            lambda m: int(m.group(1)),
        ),
        "detected_numa_nodes": (
            r"EAL:\s*Detected NUMA nodes:\s*(\d+)",
            lambda m: int(m.group(1)),
        ),
        "multi_process_socket": (
            r"EAL:\s*Multi-process socket\s+(\S+)",
            lambda m: m.group(1),
        ),
        "iova_mode": (
            r"EAL:\s*Selected IOVA mode\s+'([^']+)'",
            lambda m: m.group(1),
        ),
        "rte_version": (
            r"EAL:\s*RTE Version:\s+'([^']+)'",
            lambda m: m.group(1),
        ),
        "requested_device_unusable": (
            r"EAL:\s*Requested device\s+([0-9a-fA-F:.]+)\s+cannot be used",
            lambda m: m.group(1),
        ),
        "telemetry_status": (
            r"TELEMETRY:\s*(.+)",
            lambda m: m.group(1).strip(),
        ),
        "vfio_error": (
            r"EAL:\s*(Failed to open VFIO\S*|Cannot open /dev/vfio\S*)",
            lambda m: m.group(1),
        ),
        "hugepage_error": (
            r"EAL:\s*(Cannot get hugepage information|Not enough memory available)",
            lambda m: m.group(1),
        ),
        "not_enough_memory_socket": (
            r"EAL:\s*Not enough memory available on socket\s+(\d+)",
            lambda m: int(m.group(1)),
        ),
    }

    parsed = {}

    # 通用模式批量匹配
    for key, (pattern, extractor) in patterns.items():
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            parsed[key] = extractor(m)

    # 布尔标志：共享链接检测
    if re.search(r"EAL:\s*Detected shared linkage of DPDK", text):
        parsed["shared_linkage_detected"] = True

    # 多设备：收集所有 PCI 探测记录（改为列表，支持多网卡）
    pci_probes = re.findall(
        r"EAL:\s*Probe PCI driver:\s*(\S+).*?device:\s*([0-9a-fA-F:.]+)",
        text,
    )
    if pci_probes:
        parsed["pci_probes"] = [
            {"driver": driver, "device": device}
            for driver, device in pci_probes
        ]

    # 驱动初始化错误：精确匹配优先，降级到宽泛匹配
    m = re.search(
        r"^([A-Za-z_][A-Za-z0-9_]*)\(\):\s*(Failed to init PCI device.*)$",
        text,
        re.MULTILINE,
    )
    if m:
        source  = m.group(1).strip()
        message = m.group(2).strip()
        parsed["driver_error_source"]  = source
        parsed["driver_error_message"] = message
        parsed["driver_init_error"]    = f"{source}(): {message}"
    else:
        m2 = re.search(r"^(.*Failed to init PCI device.*)$", text, re.MULTILINE)
        if m2:
            parsed["driver_init_error"] = m2.group(1).strip()

    return parsed


def _extract_fatal_signal(tail_text):
    """从日志尾部检测崩溃信号行。"""
    m = re.search(
        r"^(Segmentation fault(?:\s*\(core dumped\))?)\s*$",
        tail_text,
        re.MULTILINE,
    )
    return m.group(1) if m else None


def extract_app_log(log_path: str, context: dict) -> None:
    """
    读取应用日志：
    - 前 APP_LOG_INIT_LINES 行做结构化解析（EAL 初始化字段）
    - 后 APP_LOG_TAIL_LINES 行保留原文用于崩溃回溯
    - 尾部单独检测崩溃信号
    """
    if not log_path:
        return

    text = safe_read_text(log_path)
    if text is None:
        context["app_log_tail"] = [f"log file not found or unreadable: {log_path}"]
        return

    lines = text.splitlines()

    # 结构化解析：只扫描前 N 行，避免在大日志上全文正则
    init_text = "\n".join(lines[:APP_LOG_INIT_LINES])
    parsed = _parse_app_log_structured(init_text)
    if parsed:
        context["app_log_parsed"] = parsed

    # 尾部原文：保留最后 200 行用于崩溃现场回溯
    tail_lines = lines[-APP_LOG_TAIL_LINES:]
    context["app_log_tail"] = tail_lines

    # 尾部单独检测崩溃信号（不依赖前 500 行）
    tail_text = "\n".join(tail_lines)
    fatal = _extract_fatal_signal(tail_text)
    if fatal:
        context["app_log_fatal_signal"] = fatal


def parse_gdb_context(pid, context, log_path=None):
    """
    解析 GDB 上下文
    """
    if not log_path:
        context["app_log_status"] = "no_path_provided"
        return
    
    steps = [
        (extract_proc_info, (pid, context)),
        (extract_dpdk_hugepage, (context,)),
        (extract_cpu_topology, (context,)),
        (extract_nic_status, (context,)),
        (extract_app_log, (log_path, context)),
    ]

    for fn, args in steps:
        try:
            fn(*args)
        except Exception as exc:
            context.setdefault("errors", []).append({
                "step":  fn.__name__,
                "type":  type(exc).__name__,
                "error": str(exc),
            })

    return context

_DPDK_USERSPACE_DRIVERS = {"vfio-pci", "uio_pci_generic", "igb_uio"}


def build_core_info_for_prompt(
    call_chain_llm: dict,
    raw_meta: dict,
    context: dict,
) -> dict:
    """
    将 parse_gdb_output 的结果 + context 转换为 prompt 可直接渲染的字段。
    call_chain_llm 已经是 to_llm_input 的输出。
    """
    is_truncated = call_chain_llm.get("analysis_mode") == "env_diagnostic"

    # ── 设备绑定：只传异常项，正常时明确置 None ──
    nic_status = context.get("nic_status", {})
    network_devs = nic_status.get("network", []) if isinstance(nic_status, dict) else []
    app_log = context.get("app_log_parsed", {})
    probed_devices = {
        p["device"] for p in app_log.get("pci_probes", [])
    }  # 例如 {"0000:00:08.0"}

    device_issues = [
        {"slot": d["pci"], "driver": d["drv"], "msg": "使用内核驱动，无法被 DPDK 接管"}
        for d in network_devs
        if d.get("drv")
        and d["drv"] not in _DPDK_USERSPACE_DRIVERS
        and d["pci"] in probed_devices  # ← 只看 DPDK 真正尝试用的设备
    ]
    # ── Hugepage ──
    hp_2m = context.get("hugepages", {}).get("hugepages_2M", {})
    try:
        total = int(hp_2m.get("total", 0))
        free  = int(hp_2m.get("free", 0))
        used  = total - free
        note  = " ⚠ 接近耗尽" if total and free < total * 0.1 else " (充足)"
        hugepage_usage = f"2M hugepages: {used}/{total} used{note}"
    except (ValueError, TypeError):
        hugepage_usage = "未知"

    # ── EAL 内部线程二次过滤兜底 ──
    _EAL_INTERNAL_FUNCS = {"mp_handle", "eal_intr_handle_events", "rte_ctrl_thread_create"}
    
    raw_abnormal = call_chain_llm.get("abnormal_threads", [])
    filtered_abnormal = [
        t for t in raw_abnormal
        if not any(f in t.get("bt_top", "") for f in _EAL_INTERNAL_FUNCS)
    ]

    # ── 把 call_chain_llm 的字段直接透传，补充 context 衍生字段 ──
    return {
        **call_chain_llm,  # 包含 analysis_mode / backtrace_quality / crash_function 等
        "is_truncated": is_truncated,
        "device_binding_issues": device_issues or None,
        "hugepage_usage": hugepage_usage,
        "abnormal_threads": filtered_abnormal,
        # 异常线程从 call_chain_llm 已有，不重复提取
    }