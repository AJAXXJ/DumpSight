from monitor.coredump_extractor.tools.parse_call_chain import DPDKFrameClassifier

_classifier = DPDKFrameClassifier()

# Maps 6-layer semantic names → 4 frontend-facing labels (backward compatible)
_LAYER_TO_TYPE: dict[str, str] = {
    "noise":    "libc",
    "libc":     "libc",
    "dpdk_pmd": "dpdk",
    "dpdk_eal": "dpdk",
    "dpdk_lib": "dpdk",
    "user_app": "user",
}

# 噪音函数前缀配置（保留供 _is_noise_frame 使用）
NOISE_PREFIXES = ("__libc_", "__recvmsg", "clone3", "start_thread")

def _is_noise_frame(frame_name):
    return frame_name.startswith(NOISE_PREFIXES)

def _classify_function(func_name, crash_func):
    """
    分类函数类型
    返回: 'crash' | 'dpdk' | 'libc' | 'user'
    """
    if func_name == crash_func:
        return "crash"
    layer = _classifier.classify(func_name)
    return _LAYER_TO_TYPE.get(layer, "user")

def build_graph_spec_tool(call_chain_graph):
    """
    构建调用图数据结构
    
    输入: call_chain_graph - 包含线程调用栈的字典
    输出: {
        nodes: [{ id, label, type, is_crash, depth, address, thread_id }],
        edges: [{ source, target, thread_id }]
    }
    
    过滤噪音帧，为每个有效函数创建节点，并建立调用边
    """
    crash_func = call_chain_graph.get("crash_function", "")
    nodes, edges, seen = [], [], set()

    all_threads = dict(call_chain_graph.get("threads", {}))
    if "main_thread" in call_chain_graph:
        main = call_chain_graph["main_thread"]
        all_threads[main["tid"]] = main

    for tid, thread in all_threads.items():
        # 过滤噪音帧
        frames = [f for f in thread.get("callstack", []) 
                  if not _is_noise_frame(f["name"])]
        
        if not frames:
            continue

        # 构建节点
        for frame in frames:
            node_id = f"{tid}_{frame['name']}"
            if node_id in seen:
                continue
            seen.add(node_id)

            nodes.append({
                "id": node_id,
                "label": frame["name"],
                "type": _classify_function(frame["name"], crash_func),
                "is_crash": frame["name"] == crash_func,
                "depth": frame["exec_depth"],
                "address": frame.get("address"),
                "thread_id": tid,
            })

        # 构建边（仅保留两端节点都存在的边）
        alive_funcs = {f["name"] for f in frames}
        for edge in thread.get("edges", []):
            caller, callee = edge["caller"], edge["callee"]
            if caller in alive_funcs and callee in alive_funcs:
                edges.append({
                    "source": f"{tid}_{caller}",
                    "target": f"{tid}_{callee}",
                    "thread_id": tid,
                })

    return {"nodes": nodes, "edges": edges}


def build_timeline_spec_tool(call_chain_graph):
    """
    构建时序线数据结构

    输入: call_chain_graph - 包含线程调用栈的字典
    输出: {
        threads: [{ tid, label, is_crash_thread }],
        events: [{ tid, func, order, is_crash, address }]
    }

    过滤噪音帧，按执行深度排序生成时序事件
    """
    crash_func = call_chain_graph.get("crash_function", "")
    crash_thread = call_chain_graph.get("main_thread", {}).get("tid", "")
    threads, events = [], []

    all_threads = dict(call_chain_graph.get("threads", {}))
    if "main_thread" in call_chain_graph:
        main = call_chain_graph["main_thread"]
        all_threads[main["tid"]] = main

    for tid, thread in all_threads.items():
        # 过滤噪音帧并按执行深度排序
        frames = sorted(
            [f for f in thread.get("callstack", [])
             if not _is_noise_frame(f["name"])],
            key=lambda x: x["exec_depth"]
        )

        if not frames:
            continue

        threads.append({
            "tid": tid,
            "label": f"Thread {tid}",
            "is_crash_thread": tid == crash_thread,
        })

        for frame in frames:
            events.append({
                "tid": tid,
                "func": frame["name"],
                "order": frame["exec_depth"],
                "is_crash": frame["name"] == crash_func,
                "address": frame.get("address"),
            })

    return {"threads": threads, "events": events}


# ── Crash Snapshot Builder ──────────────────────────────────────────────────

_POISON_BYTES: dict[int, str] = {
    0xDE: "释放后填充 (poisoned)",
    0xCD: "未初始化堆内存",
    0xFD: "堆内存守卫",
    0xAB: "未初始化栈内存",
    0xBA: "已释放内存",
    0xCC: "未初始化栈",
    0xFE: "已释放内存",
    0xDD: "已释放堆内存",
    0xF0: "已释放内存",
    0xBE: "内存填充",
}


def _detect_poison(val_str: str) -> str | None:
    try:
        val = int(val_str, 16)
    except (ValueError, TypeError):
        return None
    # 检查高位字节 (x86_64 指针中毒通常在高位)
    lead_byte = (val >> 56) & 0xFF
    if lead_byte in _POISON_BYTES:
        return _POISON_BYTES[lead_byte]
    # 也检查低 32 位中的重复模式 (32-bit 程序)
    b0 = val & 0xFF
    if b0 in _POISON_BYTES:
        mask = b0 | (b0 << 8) | (b0 << 16) | (b0 << 24)
        if (val & 0xFFFFFFFF) ^ mask < 0x100:
            return _POISON_BYTES[b0]
    return None


def _build_register_list(registers: dict, rip_module: str) -> list[dict]:
    order = [
        "rip", "rdi", "rsi", "rdx", "rsp", "rbp",
        "rax", "rbx", "rcx", "r8", "r9", "r10",
        "r11", "r12", "r13", "r14", "r15",
    ]
    result = []
    for name in order:
        val = registers.get(name)
        if val is None:
            continue
        note = None
        if name == "rip" and rip_module:
            note = rip_module
        elif name == "rdi":
            try:
                addr = int(val, 16)
                if addr == 0:
                    note = "NULL 指针"
                elif addr < 0x1000:
                    note = f"近空地址 (+{addr:#x})"
                else:
                    note = _detect_poison(val)
            except ValueError:
                pass
        result.append({"name": name, "value": val, "note": note})
    return result


def _build_stack_memory(stack_raw: dict, callstack: list) -> dict:
    frame_addrs = {f.get("address") for f in callstack if f.get("address")}

    def _annotate(values: list[str]) -> list[dict]:
        annotated = []
        for i, v in enumerate(values):
            note = None
            if v in frame_addrs:
                for f in callstack:
                    if f.get("address") == v:
                        note = f"{f['name']} 返回地址"
                        break
            annotated.append({"offset": f"+{i * 8:#06x}", "value": v, "note": note})
        return annotated

    result = {}
    if "rsp" in stack_raw:
        result["rsp"] = _annotate(stack_raw["rsp"])
    if "rbp" in stack_raw:
        result["rbp"] = _annotate(stack_raw["rbp"])
    return result


def _build_fault_info(fault_addr: str | None, crash_addr_type: dict) -> dict:
    is_near_null = False
    if fault_addr:
        try:
            is_near_null = int(fault_addr, 16) < 0x1000
        except (ValueError, TypeError):
            pass

    region_info = None
    if crash_addr_type:
        region_info = {
            "name": crash_addr_type.get("region", ""),
            "type": crash_addr_type.get("type", ""),
            "start": crash_addr_type.get("start", ""),
            "end": crash_addr_type.get("end", ""),
        }

    return {
        "address": fault_addr,
        "is_near_null": is_near_null,
        "region": region_info,
    }


def _extract_pattern_key(pattern_desc: str) -> str | None:
    if not pattern_desc:
        return None
    mapping = {
        "mempool": "mempool_exhaustion",
        "ring": "ring_assert_failure",
        "PMD": "pmd_driver_crash",
        "rte_panic": "eal_panic_abort",
        "rte_exit": "eal_panic_abort",
        "匿名": "null_ptr_in_anonymous_region",
    }
    for keyword, key in mapping.items():
        if keyword in pattern_desc:
            return key
    return None


def build_crash_snapshot_tool(
    call_chain_graph: dict,
    parsed_gdb_output: dict,
    meta: dict | None = None,
) -> dict:
    """
    构建崩溃时刻快照数据结构。

    输入:
        call_chain_graph: parse_call_chain 的输出 (CallChainResult.to_dict())
        parsed_gdb_output: GdbParseResult (含 signal, registers, stack_memory 等)
        meta: 顶层 meta 字典 (含 signal 编号、signal_name 等，可选)

    输出:
        crash_snapshot dict，含 signal / crash_point / registers / stack_memory /
        fault / crash_analysis / thread_context 七个分组。
    """
    gdb = parsed_gdb_output or {}
    llm = gdb.get("call_chain_llm") or {}
    meta = meta or {}

    # ── signal ──
    signal_info = gdb.get("signal") or {}
    signal_code = meta.get("signal") if meta.get("signal") is not None else 0

    # ── crash_point ──
    crash_frame = gdb.get("crash_frame") or {}
    crash_func_name = call_chain_graph.get("crash_function", "")
    main_thread = call_chain_graph.get("main_thread", {})
    callstack = main_thread.get("callstack", [])
    crash_node = callstack[-1] if callstack else {}

    crash_point = {
        "function": crash_func_name,
        "file": crash_frame.get("file"),
        "line": crash_frame.get("line"),
        "address": crash_node.get("address"),
        "layer": llm.get("crash_layer", ""),
    }

    # ── registers ──
    registers = gdb.get("registers") or {}
    crash_addr_type = gdb.get("crash_address_type") or {}
    rip_module = crash_addr_type.get("region", "")
    reg_list = _build_register_list(registers, rip_module)

    # ── stack_memory ──
    stack_raw = gdb.get("stack_memory") or {}
    stack_memory = _build_stack_memory(stack_raw, callstack)

    # ── fault ──
    fault = _build_fault_info(gdb.get("faulting_address"), crash_addr_type)

    # ── crash_analysis ──
    pattern_desc = llm.get("crash_pattern", "")
    crash_analysis = {
        "crash_type": gdb.get("crash_type", ""),
        "pattern": _extract_pattern_key(pattern_desc),
        "pattern_desc": pattern_desc,
        "crash_layer": llm.get("crash_layer", ""),
        "suspect_function": crash_func_name,
        "dpdk_subsystems": gdb.get("dpdk_subsystems") or [],
        "shared_libs_missing": (gdb.get("shared_libs") or {}).get("missing_libs") or [],
    }

    # ── thread_context ──
    threads = gdb.get("threads") or {}
    thread_context = {
        "total": threads.get("total", 0),
        "crashed_lwp": (threads.get("crashed") or {}).get("lwp", ""),
        "idle": threads.get("idle", 0),
        "abnormal": [
            {
                "lwp": t.get("lwp", ""),
                "bt_top": t.get("bt_top", ""),
                "role": t.get("role", ""),
            }
            for t in (threads.get("abnormal") or [])
        ],
    }

    return {
        "signal": {
            "name": signal_info.get("name", ""),
            "code": signal_code,
            "description": signal_info.get("description", ""),
        },
        "crash_point": crash_point,
        "registers": reg_list,
        "stack_memory": stack_memory,
        "fault": fault,
        "crash_analysis": crash_analysis,
        "thread_context": thread_context,
    }
