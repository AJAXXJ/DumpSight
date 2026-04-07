import os
import re
import logging

from ..constant import KEY_LS_CPU, COLLECT_TIMEOUT, APP_LOG_TAIL_LINES
from ..utils import safe_run, safe_read_text

logger = logging.getLogger(__name__)


def extract_proc_info(pid, context):
    """
    提取进程的上下文信息
    """
    if not pid:
        context["proc_snapshot_available"] = False
        context["proc_info"] = "pid unavailable"
        return

    proc_dir = f"/proc/{pid}"
    if os.path.exists(proc_dir):
        context["proc_snapshot_available"] = True
        logger.info(f"收集进程 {pid} 的上下文信息")
        context["cmdline"] = (safe_read_text(f"{proc_dir}/cmdline") or "").replace("\x00", " ")
        context["maps"] = safe_read_text(f"{proc_dir}/maps") or ""
        context["status"] = safe_read_text(f"{proc_dir}/status") or ""
        context["limits"] = safe_read_text(f"{proc_dir}/limits") or ""
    else:
        context["proc_snapshot_available"] = False
        context["proc_info"] = f"/proc/{pid} not found"


def extract_dpdk_hugepage(context):
    """
    提取 DPDK hugepage 状态
    """
    logger.info("收集 DPDK hugepage 状态")
    path_2m = "/sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages"
    path_1g = "/sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages"

    if os.path.exists(path_2m):
        context["hugepages_2M"] = (safe_read_text(path_2m) or "").strip()
    if os.path.exists(path_1g):
        context["hugepages_1G"] = (safe_read_text(path_1g) or "").strip()

    meminfo_text = safe_read_text("/proc/meminfo")
    if meminfo_text:
        context["meminfo"] = {
            line.split(":")[0]: line.split(":", 1)[1].strip()
            for line in meminfo_text.splitlines()
            if ":" in line and any(k in line for k in ["HugePages", "MemFree", "MemAvailable"])
        }


def extract_cpu_topology(context):
    """
    提取 CPU/NUMA 拓扑信息
    """
    logger.info("收集 CPU/NUMA 拓扑信息")
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


def extract_nic_status(context):
    """
    提取网卡和 PMD 状态
    """
    logger.info("收集网卡和 PMD 状态")
    r = safe_run(["dpdk-devbind.py", "--status"], timeout=COLLECT_TIMEOUT)
    if r.returncode == 0:
        context["nic_status"] = r.stdout
    else:
        context["nic_status"] = "dpdk-devbind.py unavailable"


def _parse_app_log_structured(text):
    """
    从应用日志中提取结构化字段（仅原始提取，不做分析）
    """
    parsed = {}
    if not text:
        return parsed

    # detected_lcores
    m = re.search(r"EAL:\s*Detected CPU lcores:\s*(\d+)", text)
    if m:
        parsed["detected_lcores"] = int(m.group(1))

    # detected_numa_nodes
    m = re.search(r"EAL:\s*Detected NUMA nodes:\s*(\d+)", text)
    if m:
        parsed["detected_numa_nodes"] = int(m.group(1))

    # shared_linkage_detected
    if re.search(r"EAL:\s*Detected shared linkage of DPDK", text):
        parsed["shared_linkage_detected"] = True

    # multi_process_socket
    m = re.search(r"EAL:\s*Multi-process socket\s+(\S+)", text)
    if m:
        parsed["multi_process_socket"] = m.group(1)

    # iova_mode
    m = re.search(r"EAL:\s*Selected IOVA mode\s+'([^']+)'", text)
    if m:
        parsed["iova_mode"] = m.group(1)

    # pci_probe_driver / pci_probe_device
    m = re.search(
        r"EAL:\s*Probe PCI driver:\s*([^\s]+).*?device:\s*([0-9a-fA-F:.]+)",
        text
    )
    if m:
        parsed["pci_probe_driver"] = m.group(1)
        parsed["pci_probe_device"] = m.group(2)

    # driver_init_error（优先匹配完整函数行）
    m = re.search(
        r"^([A-Za-z_][A-Za-z0-9_]*)\(\):\s*(Failed to init PCI device.*)$",
        text,
        re.MULTILINE,
    )
    if m:
        source = m.group(1).strip()
        message = m.group(2).strip()
        parsed["driver_error_source"] = source
        parsed["driver_error_message"] = message
        parsed["driver_init_error"] = f"{source}(): {message}"
    else:
        # 兜底：至少保留完整原始错误行，不返回截断值
        m2 = re.search(r"^(.*Failed to init PCI device.*)$", text, re.MULTILINE)
        if m2:
            raw = m2.group(1).strip()
            parsed["driver_init_error"] = raw

    # requested_device_unusable
    m = re.search(r"EAL:\s*Requested device\s+([0-9a-fA-F:.]+)\s+cannot be used", text)
    if m:
        parsed["requested_device_unusable"] = m.group(1)

    # telemetry_status
    m = re.search(r"TELEMETRY:\s*(.+)", text)
    if m:
        parsed["telemetry_status"] = m.group(1).strip()

    # fatal_signal
    m = re.search(r"^(Segmentation fault(?:\s*\(core dumped\))?)\s*$", text, re.MULTILINE)
    if m:
        parsed["fatal_signal"] = m.group(1)

    return parsed


def extract_app_log(log_path, context):
    """
    读取应用日志，便于离线回溯
    """
    if not log_path:
        return
    text = safe_read_text(log_path)
    if text is None:
        context["app_log_tail"] = [f"log file not found or unreadable: {log_path}"]
        return

    lines = text.splitlines()
    context["app_log_tail"] = lines[-APP_LOG_TAIL_LINES:]

    parsed = _parse_app_log_structured(text)
    if parsed:
        context["app_log_parsed"] = parsed


def parse_gdb_context(pid, context, log_path=None):
    """
    解析 GDB 上下文
    """
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
        except Exception as exc:  # 单项失败不阻断
            context.setdefault("errors", []).append(f"{fn.__name__}: {exc}")

    return context