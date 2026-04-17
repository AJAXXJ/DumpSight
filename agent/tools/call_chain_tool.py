# 噪音函数前缀配置
NOISE_PREFIXES = ("__libc_", "__recvmsg", "clone3", "start_thread")

def _is_noise_frame(frame_name):
    """判断是否为噪音帧"""
    return frame_name.startswith(NOISE_PREFIXES)

def _classify_function(func_name, crash_func):
    """
    分类函数类型
    返回: 'crash' | 'dpdk' | 'libc' | 'user'
    """
    if func_name == crash_func:
        return "crash"
    if "rte_" in func_name or "dpdk" in func_name.lower():
        return "dpdk"
    if func_name.startswith("__") or func_name.startswith("_"):
        return "libc"
    return "user"

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

    for tid, thread in call_chain_graph.get("threads", {}).items():
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

    for tid, thread in call_chain_graph.get("threads", {}).items():
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
