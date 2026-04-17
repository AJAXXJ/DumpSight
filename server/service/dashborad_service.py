import datetime

from agent.output.report_formatter import _get
from agent.tools.call_chain_tool import build_graph_spec_tool, build_timeline_spec_tool
from agent.tools.telemetry_feature_tool import log_1s_statistic, log_5s_statistic
from server.repository.client_redis import (
    get_dpdk_core_info,
    get_dpdk_info,
    get_dpdk_log,
)
from server.repository.client_repository import get_client_info
from server.repository.core_repositiry import get_core_info
from server.tools.metrics_timeseries_collector import process_and_get_timeseries


def dashborad_raw_json_service(request_json):
    """
    前端获取原始 json 数据
    """
    names = request_json.get("names")

    client_id = request_json.get("client_id")
    pid = request_json.get("pid")
    timestamp = request_json.get("timestamp")

    core_info = get_core_info(client_id, pid, timestamp)

    state = core_info["state"]

    return _get(state, *names, default="暂无此参数")


def dashborad_render_report_service(client_id, pid, timestamp):
    """
    前端渲染崩溃报告 调用链数据 异常时序数据
    """
    core_info = get_core_info(client_id, pid, timestamp)

    redis_core_info = get_dpdk_core_info(client_id, pid, timestamp)

    crash_timestamp = redis_core_info["core_timestamp"]
    call_chain_graph = redis_core_info["meta"]["parsed_gdb_output"]["call_chain_graph"]

    graph_spec = build_graph_spec_tool(call_chain_graph)
    timeline_spec = build_timeline_spec_tool(call_chain_graph)

    return {
        "crash_time": datetime.fromtimestamp(crash_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "report": core_info["report"],
        "process_time": core_info["process_time"],
        "analyse_time": core_info["analyse_time"],
        "total_time": core_info["total_time"],
        "graph_spec": graph_spec,
        "timeline_spec": timeline_spec,
    }


def dashborad_client_info_service(client_id):
    """
    前端获取指定客户端信息
    """
    return get_client_info(client_id)


def dashborad_instance_info_service(client_id, pid):
    """
    前端获取指定DPDK实例信息
    """
    return get_dpdk_info(client_id, pid)


def dashborad_instance_card_info_service(client_id, pid, seconds):
    """
    前端获取指定秒数窗口期日志聚合信息
    """
    metrics_1s = get_dpdk_log(client_id, pid, "1s", seconds)
    metrics_5s = get_dpdk_log(client_id, pid, "5s", seconds)

    timeseries_data = process_and_get_timeseries(metrics_1s, metrics_5s)

    stat1 = log_1s_statistic(metrics_1s)
    stat5 = log_5s_statistic(metrics_5s)

    return {
        "summary_data": {
            # 进程基本信息
            "process": stat1["process"],  # pid / is_alive / type / timestamp / window
            # 端口流量 1s 精度，计算了 delta + rate
            "ports": {
                port_id: {
                    "link": p["link"],
                    "rx": p["rx"],  # pps / bps / ierrors / nombuf
                    "tx": p["tx"],
                    "queue": p["queue"],  # imbalance_ratio / active_queues
                    "traffic_pattern": p[
                        "traffic_pattern"
                    ],  # multicast/broadcast/undersize ratio
                }
                for port_id, p in stat1["ports"].items()
            },
            # lcore 利用率
            "lcore": stat1["lcore"],  # per-lcore usage_ratio + __summary__
            # mempool
            "mempool": stat1["mempool"],  # free_ratio / cache_pressure / size
            # heap
            "heap": stat1["heap"],  # free_ratio / fragmentation / alloc_count
            # 5s 窗口聚合
            "ports_5s": stat5["ports"],
            "lcore_5s": stat5["lcore"],
        },
        "timeseries_data": timeseries_data,
    }
