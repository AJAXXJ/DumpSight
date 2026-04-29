import datetime
from server.repository.case_repository import get_all_case
from server.service.client_service import is_client_alive
from tools.common_utils import format_datetime
from agent.output.report_formatter import _get
from agent.tools.call_chain_tool import build_graph_spec_tool, build_timeline_spec_tool
from agent.tools.telemetry_feature_tool import log_1s_statistic, log_5s_statistic
from server.repository.client_redis import (
    get_client_running_instances,
    get_dpdk_core_info,
    get_dpdk_info,
    get_dpdk_log,
)
from server.repository.client_repository import get_all_client_info, get_client_info
from server.repository.core_repository import (
    get_core_info,
    get_core_list,
    get_core_page,
)
from server.tools.metrics_timeseries_collector import process_and_get_timeseries
from tools.minio_util import get_minio_util


def dashboard_report_list_service(page_index, page_size):
    """
    前端获取所有崩溃报告
    """
    core_page = get_core_page(page_index, page_size)
    core_list = core_page["items"]

    report_list = []
    for core in core_list:

        redis_core_info = get_dpdk_core_info(
            core["client_id"], core["pid"], core["timestamp"]
        )

        crash_timestamp = redis_core_info["core_timestamp"]

        report_list.append(
            {
                "id": core["id"],
                "client_id": core["client_id"],
                "pid": core["pid"],
                "timestamp": core["timestamp"],
                "process_time": core["process_time"],
                "analyse_time": core["analyse_time"],
                "total_time": core["total_time"],
                "crash_time": datetime.datetime.fromtimestamp(crash_timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "create_time": datetime.datetime.fromisoformat(
                    core["create_time"]
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return {
        "total": core_page["total"],
        "page": core_page["page"],
        "page_size": core_page["page_size"],
        "items": report_list,
    }


def dashboard_raw_json_service(search_dict):
    """
    前端获取原始 json 数据
    """
    names = search_dict.get("names")

    client_id = search_dict.get("client_id")
    pid = search_dict.get("pid")
    timestamp = search_dict.get("timestamp")

    core_info = get_core_info(client_id, pid, timestamp)

    state = core_info["state"]

    return _get(state, *names, default="暂无此参数")


def dashboard_render_report_service(client_id, pid, timestamp):
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
        "crash_time": datetime.datetime.fromtimestamp(crash_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "report": core_info["report"],
        "process_time": core_info["process_time"],
        "analyse_time": core_info["analyse_time"],
        "total_time": core_info["total_time"],
        "graph_spec": graph_spec,
        "timeline_spec": timeline_spec,
    }


def dashboard_client_list_service():
    """
    前端获取所有客户端信息
    """
    client_list = get_all_client_info()
    client_front_list = []

    for client in client_list:

        client_id = client["client_id"]

        environment = client["environment"]

        os = environment["os"]
        dpdk_version = environment["version"]
        hostname = environment["hostname"]

        running_instances_pid_nums = len(get_client_running_instances(client_id))

        create_time = format_datetime(client["create_time"])

        client_front_list.append(
            {
                "id": client["id"],
                "client_id": client_id,
                "os": os,
                "hostname": hostname,
                "dpdk_version": dpdk_version,
                "running_instances_pid_nums": running_instances_pid_nums,
                "created_time": create_time,
                "alive": is_client_alive(client),
            }
        )

    return client_front_list


def dashboard_instance_list_service(client_id):
    """
    前端获取指定客户端正在运行实例列表
    """
    instance_list = get_client_running_instances(client_id)
    return [
        {**instance, "start_time": format_datetime(instance.get("start_time"))}
        for instance in instance_list
    ]


def dashboard_client_info_service(client_id):
    """
    前端获取指定客户端信息
    """
    return get_client_info(client_id)


def dashboard_instance_info_service(client_id, pid):
    """
    前端获取指定DPDK实例信息
    """
    return get_dpdk_info(client_id, pid)


def dashboard_instance_timeseries_info_service(client_id, pid, seconds):
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


def dashboard_statics_service():
    """
    前端统计数据获取
    """
    client_list = get_all_client_info()
    client_nums = len(client_list)

    pid_nums = 0
    for client in client_list:
        client_id = client["client_id"]
        pid_nums += len(get_client_running_instances(client_id))

    core_nums = len(get_core_list())

    case_nums = len(get_all_case())

    return {
        "client_nums": client_nums,
        "pid_nums": pid_nums,
        "core_nums": core_nums,
        "case_nums": case_nums,
    }


