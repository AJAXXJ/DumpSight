from collections import deque, defaultdict
from typing import Dict, List, Any
import time


class MetricsTimeSeriesCollector:
    def __init__(self, max_points_1s=300, max_points_5s=180):
        """
        初始化时序数据收集器

        Args:
            max_points_1s: 1s 数据保留的最大点数（默认 300 = 5 分钟）
            max_points_5s: 5s 数据保留的最大点数（默认 180 = 15 分钟）
        """
        self.max_points_1s = max_points_1s
        self.max_points_5s = max_points_5s

        # 1s 序列队列
        self.rx_pps = deque(maxlen=max_points_1s)
        self.tx_pps = deque(maxlen=max_points_1s)
        self.rx_bps = deque(maxlen=max_points_1s)
        self.tx_bps = deque(maxlen=max_points_1s)
        self.rx_ierrors = deque(maxlen=max_points_1s)
        self.rx_nombuf = deque(maxlen=max_points_1s)
        self.q_ipackets = defaultdict(
            lambda: deque(maxlen=max_points_1s)
        )  # 每个队列一条线
        self.mempool_free_ratio = defaultdict(lambda: deque(maxlen=max_points_1s))

        # 5s 序列队列
        self.lcore_usage = defaultdict(
            lambda: deque(maxlen=max_points_5s)
        )  # 每个 lcore 一条线
        self.rx_missed_errors = deque(maxlen=max_points_5s)
        self.heap_free_ratio = defaultdict(lambda: deque(maxlen=max_points_5s))

        # 用于计算 delta 的上一次值
        self.last_1s_stats = {}
        self.last_5s_stats = {}

    def process_metrics_1s(self, metrics):
        """处理 1s 指标数据"""
        timestamp = metrics.get("timestamp", time.time())
        ethdev_stats = metrics.get("ethdev_stats", {})
        mempool_stats = metrics.get("mempool_stats", {})

        # 处理第一个网卡（port 0）
        if "0" in ethdev_stats:
            stats = ethdev_stats["0"]
            port_key = "0"

            # 计算 delta（如果有上一次的数据）
            if port_key in self.last_1s_stats:
                last = self.last_1s_stats[port_key]

                # rx/tx pps (packets per second)
                rx_pps = stats["ipackets"] - last["ipackets"]
                tx_pps = stats["opackets"] - last["opackets"]

                # rx/tx bps (bytes per second * 8 for bits)
                rx_bps = (stats["ibytes"] - last["ibytes"]) * 8
                tx_bps = (stats["obytes"] - last["obytes"]) * 8

                # errors
                rx_ierrors = stats["ierrors"] - last["ierrors"]
                rx_nombuf = stats["rx_nombuf"] - last["rx_nombuf"]

                # 添加到队列
                self.rx_pps.append({"timestamp": timestamp, "value": rx_pps})
                self.tx_pps.append({"timestamp": timestamp, "value": tx_pps})
                self.rx_bps.append({"timestamp": timestamp, "value": rx_bps})
                self.tx_bps.append({"timestamp": timestamp, "value": tx_bps})
                self.rx_ierrors.append({"timestamp": timestamp, "value": rx_ierrors})
                self.rx_nombuf.append({"timestamp": timestamp, "value": rx_nombuf})

                # 每个队列的 ipackets delta
                for i, (curr_pkt, last_pkt) in enumerate(
                    zip(stats["q_ipackets"], last["q_ipackets"])
                ):
                    delta = curr_pkt - last_pkt
                    if delta > 0:  # 只记录有流量的队列
                        self.q_ipackets[f"queue_{i}"].append(
                            {"timestamp": timestamp, "value": delta}
                        )

            # 保存当前值用于下次计算 delta
            self.last_1s_stats[port_key] = {
                "ipackets": stats["ipackets"],
                "opackets": stats["opackets"],
                "ibytes": stats["ibytes"],
                "obytes": stats["obytes"],
                "ierrors": stats["ierrors"],
                "rx_nombuf": stats["rx_nombuf"],
                "q_ipackets": stats["q_ipackets"].copy(),
            }

        # mempool free ratio
        for pool_name, pool_stats in mempool_stats.items():
            total = pool_stats["size"]
            free = pool_stats["common_pool_count"] + pool_stats["total_cache_count"]
            free_ratio = (free / total * 100) if total > 0 else 0
            self.mempool_free_ratio[pool_name].append(
                {"timestamp": timestamp, "value": free_ratio}
            )

    def process_metrics_5s(self, metrics):
        """处理 5s 指标数据"""
        timestamp = metrics.get("timestamp", time.time())
        ethdev_xstats = metrics.get("ethdev_xstats", {})
        lcore_usage = metrics.get("lcore_usage", {})
        heap_stats = metrics.get("heap_stats", {})

        # rx_missed_errors delta
        if "0" in ethdev_xstats:
            xstats = ethdev_xstats["0"]
            port_key = "0"

            if port_key in self.last_5s_stats:
                last = self.last_5s_stats[port_key]
                rx_missed_delta = xstats["rx_missed_errors"] - last["rx_missed_errors"]
                self.rx_missed_errors.append(
                    {"timestamp": timestamp, "value": rx_missed_delta}
                )

            self.last_5s_stats[port_key] = {
                "rx_missed_errors": xstats["rx_missed_errors"]
            }

        # lcore usage ratio
        for lcore_id, lcore_data in lcore_usage.items():
            usage_ratios = lcore_data.get("usage_ratio", [])
            lcore_ids = lcore_data.get("lcore_ids", [])

            for i, (lid, ratio_str) in enumerate(zip(lcore_ids, usage_ratios)):
                # 解析 "0.00%" 格式
                ratio_value = float(ratio_str.rstrip("%"))
                self.lcore_usage[f"lcore_{lid}"].append(
                    {"timestamp": timestamp, "value": ratio_value}
                )

        # heap free ratio
        for heap_id, heap_data in heap_stats.items():
            heap_size = heap_data["Heap_size"]
            free_size = heap_data["Free_size"]
            free_ratio = (free_size / heap_size * 100) if heap_size > 0 else 0
            heap_name = heap_data.get("Name", f"heap_{heap_id}")
            self.heap_free_ratio[heap_name].append(
                {"timestamp": timestamp, "value": free_ratio}
            )

    def get_timeseries_data(self):
        """
        返回所有时序数据，格式适合前端折线图展示

        Returns:
            包含所有时序数据的字典，按类别分组
        """
        return {
            # 1s 序列
            "traffic": {
                "rx_pps": list(self.rx_pps),
                "tx_pps": list(self.tx_pps),
                "rx_bps": list(self.rx_bps),
                "tx_bps": list(self.tx_bps),
            },
            "errors": {
                "rx_ierrors": list(self.rx_ierrors),
                "rx_nombuf": list(self.rx_nombuf),
            },
            "queue_distribution": {
                queue_name: list(queue_data)
                for queue_name, queue_data in self.q_ipackets.items()
            },
            "mempool": {
                pool_name: list(pool_data)
                for pool_name, pool_data in self.mempool_free_ratio.items()
            },
            # 5s 序列
            "lcore_usage": {
                lcore_name: list(lcore_data)
                for lcore_name, lcore_data in self.lcore_usage.items()
            },
            "rx_missed": list(self.rx_missed_errors),
            "heap": {
                heap_name: list(heap_data)
                for heap_name, heap_data in self.heap_free_ratio.items()
            },
        }


def process_and_get_timeseries(metrics_1s_list, metrics_5s_list):
    """
    处理 metrics 列表并返回时序数据

    Args:
        metrics_1s_list: 1s 指标数据列表
        metrics_5s_list: 5s 指标数据列表

    Returns:
        适合前端折线图展示的时序数据字典
    """
    collector = MetricsTimeSeriesCollector()

    # 处理所有 1s 数据
    for metrics in metrics_1s_list:
        collector.process_metrics_1s(metrics)

    # 处理所有 5s 数据
    for metrics in metrics_5s_list:
        collector.process_metrics_5s(metrics)

    return collector.get_timeseries_data()
