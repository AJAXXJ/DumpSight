import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

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

_DPDK_USERSPACE_DRIVERS = {"vfio-pci", "uio_pci_generic", "igb_uio"}

_EAL_INTERNAL_FUNCS = {"mp_handle", "eal_intr_handle_events", "rte_ctrl_thread_create"}


class SystemContextCollector:
    """
    采集系统运行时快照：/proc 信息、hugepage、CPU 拓扑、网卡状态、应用日志。
    collect() 返回 context dict，不依赖外部 out-param。
    """

    def collect(self, pid: str | None, log_path: str | None = None) -> dict:
        context: dict = {}
        steps = [
            (self._collect_proc_info, (pid,)),
            (self._collect_hugepage, ()),
            (self._collect_cpu_topology, ()),
            (self._collect_nic_status, ()),
            (self._collect_app_log, (log_path,)),
        ]

        with ThreadPoolExecutor(max_workers=len(steps)) as executor:
            futures = {executor.submit(fn, context, *args): fn.__name__ for fn, args in steps}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    context.setdefault("errors", []).append({
                        "step":  futures[future],
                        "type":  type(exc).__name__,
                        "error": str(exc),
                    })

        return context

    # ── /proc ──────────────────────────────────────────────────────────────

    def _collect_proc_info(self, context: dict, pid: str | None) -> None:
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

    # ── Hugepage ────────────────────────────────────────────────────────────

    def _collect_hugepage(self, context: dict) -> None:
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

    # ── CPU topology ────────────────────────────────────────────────────────

    def _collect_cpu_topology(self, context: dict) -> None:
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

    # ── NIC / DPDK binding ─────────────────────────────────────────────────

    def _collect_nic_status(self, context: dict) -> None:
        r = safe_run(["dpdk-devbind.py", "--status"], timeout=COLLECT_TIMEOUT)
        if r.returncode != 0:
            context["nic_status"] = {"error": "dpdk-devbind.py unavailable"}
            return
        context["nic_status"] = parse_nic_status(r.stdout)

    # ── Application log ────────────────────────────────────────────────────

    def _collect_app_log(self, context: dict, log_path: str | None) -> None:
        if not log_path:
            context["app_log_status"] = "no_path_provided"
            return

        text = safe_read_text(log_path)
        if text is None:
            context["app_log_tail"] = [f"log file not found or unreadable: {log_path}"]
            return

        lines = text.splitlines()
        init_text = "\n".join(lines[:APP_LOG_INIT_LINES])
        parsed = _parse_app_log_structured(init_text)
        if parsed:
            context["app_log_parsed"] = parsed

        tail_lines = lines[-APP_LOG_TAIL_LINES:]
        context["app_log_tail"] = tail_lines

        tail_text = "\n".join(tail_lines)
        fatal = _extract_fatal_signal(tail_text)
        if fatal:
            context["app_log_fatal_signal"] = fatal


# ── Pure parsing helpers (module-level, no side effects) ──────────────────


def parse_nic_status(raw: str) -> dict:
    """将 dpdk-devbind.py --status 的原始输出解析为结构化字典。"""
    result = {v: [] for v in dict.fromkeys(_NIC_SECTION_MAP.values())}
    current = None

    for line in raw.splitlines():
        line = line.strip()
        if not line or re.match(r"^=+$", line):
            continue

        lower = line.lower()
        matched_section = next(
            (key for key in _NIC_SECTION_MAP if key in lower), None
        )
        if matched_section:
            current = _NIC_SECTION_MAP[matched_section]
            continue

        if line.lower().startswith("no ") and "detected" in line.lower():
            continue

        if current is None:
            continue

        m = re.match(r"^([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f])\s+'([^']+)'(.*)$", line)
        if not m:
            continue

        pci, desc, rest = m.group(1), m.group(2), m.group(3)
        result[current].append({
            "pci":    pci,
            "desc":   desc,
            "if":     _kv(rest, "if"),
            "drv":    _kv(rest, "drv"),
            "unused": _kv(rest, "unused"),
            "active": "*Active*" in rest,
        })

    return result


def _kv(text: str, key: str) -> str:
    m = re.search(rf"{key}=(\S+)", text)
    return m.group(1) if m else ""


def _parse_app_log_structured(text: str) -> dict:
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
    for key, (pattern, extractor) in patterns.items():
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            parsed[key] = extractor(m)

    if re.search(r"EAL:\s*Detected shared linkage of DPDK", text):
        parsed["shared_linkage_detected"] = True

    pci_probes = re.findall(
        r"EAL:\s*Probe PCI driver:\s*(\S+).*?device:\s*([0-9a-fA-F:.]+)",
        text,
    )
    if pci_probes:
        parsed["pci_probes"] = [
            {"driver": driver, "device": device}
            for driver, device in pci_probes
        ]

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


def _extract_fatal_signal(tail_text: str) -> str | None:
    m = re.search(
        r"^(Segmentation fault(?:\s*\(core dumped\))?)\s*$",
        tail_text,
        re.MULTILINE,
    )
    return m.group(1) if m else None


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

    nic_status = context.get("nic_status", {})
    network_devs = nic_status.get("network", []) if isinstance(nic_status, dict) else []
    app_log = context.get("app_log_parsed", {})
    probed_devices = {p["device"] for p in app_log.get("pci_probes", [])}

    device_issues = [
        {"slot": d["pci"], "driver": d["drv"], "msg": "使用内核驱动，无法被 DPDK 接管"}
        for d in network_devs
        if d.get("drv")
        and d["drv"] not in _DPDK_USERSPACE_DRIVERS
        and d["pci"] in probed_devices
    ]

    hp_2m = context.get("hugepages", {}).get("hugepages_2M", {})
    try:
        total = int(hp_2m.get("total", 0))
        free  = int(hp_2m.get("free", 0))
        used  = total - free
        note  = " ⚠ 接近耗尽" if total and free < total * 0.1 else " (充足)"
        hugepage_usage = f"2M hugepages: {used}/{total} used{note}"
    except (ValueError, TypeError):
        hugepage_usage = "未知"

    raw_abnormal = call_chain_llm.get("abnormal_threads", [])
    filtered_abnormal = [
        t for t in raw_abnormal
        if not any(f in t.get("bt_top", "") for f in _EAL_INTERNAL_FUNCS)
    ]

    # 从 raw_meta 中补充 crash_locals 和 crash_type（call_chain_llm 不含这些字段）
    gdb_output = raw_meta.get("parsed_gdb_output", {})
    crash_locals: dict = gdb_output.get("crash_locals", {})
    crash_type: str = gdb_output.get("crash_type", "")

    # 裁剪 crash_locals：仅保留标量或短值，避免 leak 数组撑爆 prompt
    _MAX_LOCAL_VAL_LEN = 120
    trimmed_locals = {
        k: (v if len(str(v)) <= _MAX_LOCAL_VAL_LEN else str(v)[:_MAX_LOCAL_VAL_LEN] + "…")
        for k, v in crash_locals.items()
        if k != "leak"  # leak 数组体积太大，对诊断无增量价值
    }

    return {
        **call_chain_llm,
        "is_truncated": is_truncated,
        "device_binding_issues": device_issues or None,
        "hugepage_usage": hugepage_usage,
        "abnormal_threads": filtered_abnormal,
        "crash_type": crash_type,
        "crash_locals": trimmed_locals or None,
    }


# ── Backward-compatible free functions ────────────────────────────────────

_default_collector = SystemContextCollector()


def parse_gdb_context(pid, context, log_path=None):
    """旧接口兼容：将采集结果合并到调用方传入的 context dict 中并返回。"""
    collected = _default_collector.collect(pid, log_path)
    context.update(collected)
    return context


def extract_proc_info(pid, context):
    _default_collector._collect_proc_info(context, pid)


def extract_dpdk_hugepage(context):
    _default_collector._collect_hugepage(context)


def extract_cpu_topology(context):
    _default_collector._collect_cpu_topology(context)


def extract_nic_status(context):
    _default_collector._collect_nic_status(context)


def extract_app_log(log_path: str, context: dict) -> None:
    _default_collector._collect_app_log(context, log_path)
