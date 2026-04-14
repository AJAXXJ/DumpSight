import platform
import socket
import subprocess
import time
import json
import threading
from collections import deque
from monitor.dpdk_tools.cpu_layout import get_cpu_layout_simple
from monitor.dpdk_tools.dpdk_hugepages import get_hugepage_status
from monitor.dpdk_tools.dpdk_devbind_helper import (
    get_device_status,
    get_network_devices,
)
from monitor.dpdk_tools import dpdk_telemetry as telemetry
from tools.logger import logger


def environment():
    """
    Collects the DPDK context information.
    """

    return {
        "version": dpdk_version(),
        "cpu": get_cpu_layout_simple(),  # CPU 拓扑 / 核心分布信息
        "hugepage": get_hugepage_status(),  # HugePage 状态
        "devbind": get_device_status(),  # 网卡设备绑定状态
        "hostname": socket.gethostname(),  # 获取主机名
        "os": platform.system() + " " + platform.version(),  # 获取操作系统和版本
    }


def dpdk_version():
    """
    Retrieves the DPDK version using pkg-config.
    """
    try:
        result = subprocess.run(
            ["pkg-config", "--modversion", "libdpdk"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        version = result.stdout.strip()
        return version
    except subprocess.CalledProcessError as e:
        print("Error running pkg-config:", e.stderr.strip())
        return ""
    except FileNotFoundError:
        print("pkg-config not found")
        return ""


def dpdk_info(file_prefix=None, instance=None):
    """
    Retrieves information about the DPDK application.
    """
    result = telemetry.query("/info", file_prefix=file_prefix, instance=instance)[
        "info"
    ]
    return {
        "DPDK Version": result["version"],
        "PID": result["pid"],
        "Max Output": result["max_output_len"],
    }


def is_dpdk_alive(file_prefix="rte"):
    """
    Checks if the DPDK application is alive by looking for the telemetry socket.
    """
    socks = telemetry.find_sockets(telemetry.get_dpdk_runtime_dir(file_prefix))
    return len(socks) > 0

def _cmd_key(cmd: str, params: dict) -> str:
    """生成与 DPDK telemetry 响应严格匹配的命令键"""
    return cmd + "," + json.dumps(params, separators=(',', ':'))


def poll_1s(file_prefix=None, instance=None):
    kw = dict(file_prefix=file_prefix, instance=instance)

    pre = telemetry.query_batch(
        ["/ethdev/list", "/mempool/list", "/dmadev/list"],
        **kw,
    )

    ports = pre["/ethdev/list"].get("/ethdev/list", [])
    mempool_names = pre["/mempool/list"].get("/mempool/list") or []
    dma_ids = pre["/dmadev/list"].get("/dmadev/list") or []

    cmds = (
        [f"/ethdev/stats,{p}" for p in ports]
        + [f"/ethdev/link_status,{p}" for p in ports]
        + [f"/mempool/info,{n}" for n in mempool_names]
        + [f"/dmadev/stats,{d}" for d in dma_ids]
        + ["/ipsec/sa/stats"]
    )
    results = telemetry.query_batch(cmds, **kw)

    ethdev_stats = {
        p: results.get(f"/ethdev/stats,{p}", {}).get("/ethdev/stats", {})
        for p in ports
    }
    ethdev_link = {
        p: results.get(f"/ethdev/link_status,{p}", {}).get("/ethdev/link_status", {})
        for p in ports
    }
    mempool_stats = {
        n: results.get(f"/mempool/info,{n}", {}).get("/mempool/info", {})
        for n in mempool_names
    }
    dma_stats = {
        d: results.get(f"/dmadev/stats,{d}", {}).get("/dmadev/stats", {})
        for d in dma_ids
    }
    ipsec_stats = results.get("/ipsec/sa/stats", {}).get("/ipsec/sa/stats", {})

    return {
        "is_alive": is_dpdk_alive(file_prefix or "rte"),
        "ethdev_stats": ethdev_stats,
        "ethdev_link": ethdev_link,
        "mempool_stats": mempool_stats,
        **({"dma_stats": dma_stats}   if dma_ids   else {}),
        **({"ipsec_stats": ipsec_stats} if ipsec_stats else {}),
    }


def poll_5s(file_prefix=None, instance=None):
    kw = dict(file_prefix=file_prefix, instance=instance)

    pre = telemetry.query_batch(
        [
            "/ethdev/list",
            "/eal/lcore/list",
            "/eal/heap_list",
            "/eventdev/dev_list",
            "/cnxk/nix/list",
        ],
        **kw,
    )

    ports = pre["/ethdev/list"].get("/ethdev/list", [])
    lcore_list = pre["/eal/lcore/list"].get("/eal/lcore/list", [])
    heap_list = pre["/eal/heap_list"].get("/eal/heap_list", [])
    dev_list = pre["/eventdev/dev_list"].get("/eventdev/dev_list") or []
    nix_list = pre["/cnxk/nix/list"].get("/cnxk/nix/list", [])

    cmds = (
        [f"/ethdev/xstats,{p}" for p in ports]
        + [f"/eal/lcore/usage,{l}" for l in lcore_list]
        + [f"/eal/heap_info,{h}" for h in heap_list]
        + [f"/eventdev/dev_xstats,{d}" for d in dev_list]
        + [f"/cnxk/nix/info,{n}" for n in nix_list]
    )
    results = telemetry.query_batch(cmds, **kw)

    xstats = {}
    for port_id in ports:
        raw = results.get(f"/ethdev/xstats,{port_id}", {}).get("/ethdev/xstats", {})
        # xstats 可能是 list[{name, value}] 或直接是 dict，两种都处理
        if isinstance(raw, list):
            xstats[port_id] = {item["name"]: item["value"] for item in raw}
        else:
            xstats[port_id] = raw  # 已经是 dict（你的版本就是 dict）

    lcore_usage = {
        l: results.get(f"/eal/lcore/usage,{l}", {}).get("/eal/lcore/usage", {})
        for l in lcore_list
    }
    heap_stats = {
        h: results.get(f"/eal/heap_info,{h}", {}).get("/eal/heap_info", {})
        for h in heap_list
    }
    eventdev_stats = {
        d: results.get(f"/eventdev/dev_xstats,{d}", {}).get("/eventdev/dev_xstats", {})
        for d in dev_list
    }
    nix_stats = {
        n: results.get(f"/cnxk/nix/info,{n}", {}).get("/cnxk/nix/info", {})
        for n in nix_list
    }

    return {
        "ethdev_xstats": xstats,
        "lcore_usage": lcore_usage,
        "heap_stats": heap_stats,
        **({"eventdev_stats": eventdev_stats} if dev_list  else {}),
        **({"nix_stats": nix_stats}         if nix_list else {}),
    }

def check_devbind_on_anomaly():
    """
    Checks for anomalies in the device binding status.
    When executing DPDK applications traggered.
    """
    net = get_network_devices()
    alert = []

    for dev in net["kernel_bound"]:
        alert.append(
            {
                "slot": dev["slot"],
                "device": dev["device"],
                "driver": dev["driver"],
                "iface": dev["iface"],
                "msg": "Network card has switched back to kernel driver",
            }
        )
    for dev in net["no_driver"]:
        alert.append(
            {
                "slot": dev["slot"],
                "device": dev["device"],
                "msg": "Network card has no driver bound",
            }
        )

    return alert  # DPDK 设备绑定一致性检查


class DPDKLiveMonitor:
    """
    Monitors multiple DPDK instances concurrently, buffers and uploads in batches.
    Supports dynamic add/remove of instances.
    """

    def __init__(self, config, instances=None):
        self.config = config
        self._buffer = deque()
        self._buffer_lock = threading.Lock()

        self._workers = (
            {}
        )  # key -> {"thread": t, "stop_event": e, "instance": instance}
        self._global_stop = threading.Event()
        self._lock = threading.Lock()

        self.instances = instances or []

    def _make_key(self, instance: dict):
        pid = instance.get("pid")
        instance_id = instance.get("instance")
        return (
            int(pid) if pid is not None else None,
            instance.get("file_prefix"),
            int(instance_id) if instance_id is not None else None,
        )

    def _store(self, data):
        with self._buffer_lock:
            self._buffer.append(data)

    def flush(self):
        with self._buffer_lock:
            if not self._buffer:
                return []
            batch = list(self._buffer)
            self._buffer.clear()
        return batch

    def _collect_one(self, instance, stop_event):
        tick = 0
        pid = instance.get("pid")
        file_prefix = instance.get("file_prefix")
        instance_id = instance.get("instance")

        ident = {
            "pid": pid
        }

        while not stop_event.is_set() and not self._global_stop.is_set():
            t0 = time.time()
            try:
                alive = is_dpdk_alive(file_prefix or "rte")

                if not alive:
                    self._store(
                        {
                            **ident,
                            "timestamp": t0,
                            "type": "heartbeat",
                            "is_alive": False,
                        }
                    )
                    stop_event.wait(1.0)
                    tick += 1
                    continue

                self._store(
                    {
                        **ident,
                        "timestamp": t0,
                        "type": "1s",
                        **poll_1s(file_prefix, instance_id),
                    }
                )

                if tick % 5 == 0:
                    self._store(
                        {
                            **ident,
                            "timestamp": t0,
                            "type": "5s",
                            **poll_5s(file_prefix, instance_id),
                        }
                    )

            except Exception as e:
                logger.error(f"[Collect error] {file_prefix}:{instance_id} {e}")
                self._store(
                    {
                        **ident,
                        "timestamp": t0,
                        "type": "error",
                        "error": str(e),
                    }
                )

            tick += 1
            stop_event.wait(max(0, 1.0 - (time.time() - t0)))

    def add_instance(self, instance: dict):
        """
        Add one instance to monitoring.
        """
        if self._global_stop.is_set():
            return
        key = self._make_key(instance)

        with self._lock:
            if key in self._workers:
                return

            stop_event = threading.Event()
            t = threading.Thread(
                target=self._collect_one,
                args=(instance, stop_event),
                name=f"dpdk-{instance.get('exe_name')}-{instance.get('file_prefix')}-{instance.get('instance')}",
                daemon=True,
            )

            self._workers[key] = {
                "thread": t,
                "stop_event": stop_event,
                "instance": instance,
            }

            t.start()

    def remove_instance(self, instance: dict):
        """
        Stop one instance from monitoring.
        """
        key = self._make_key(instance)

        with self._lock:
            worker = self._workers.pop(key, None)

        if not worker:
            return

        worker["stop_event"].set()
        worker["thread"].join(timeout=5)

    def sync_instances(self, instances):
        """
        Sync current running instances with monitor list.
        Add new ones and remove non-running ones.
        """
        new_map = {self._make_key(i): i for i in instances}

        with self._lock:
            old_keys = set(self._workers.keys())

        new_keys = set(new_map.keys())

        # add
        for key in new_keys - old_keys:
            self.add_instance(new_map[key])

        # remove
        for key in old_keys - new_keys:
            with self._lock:
                worker = self._workers.pop(key, None)  # 原子 pop
            if worker:
                worker["stop_event"].set()
                worker["thread"].join(timeout=5)

    def start(self):
        """
        Start initial monitoring.
        """
        for instance in self.instances:
            self.add_instance(instance)

    def stop(self):
        """
        Stop all monitoring threads.
        """
        self._global_stop.set()

        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()

        for worker in workers:
            worker["stop_event"].set()

        for worker in workers:
            worker["thread"].join(timeout=5)


_monitor_instance: DPDKLiveMonitor | None = None
_monitor_lock = threading.Lock()


def get_monitor(config=None, intances=None) -> DPDKLiveMonitor:
    """
    返回全局唯一的 DPDKLiveMonitor 实例。
    仅第一次调用时 config 和 instances 生效，后续调用直接返回已有实例。
    """
    global _monitor_instance
    if _monitor_instance is None:
        with _monitor_lock:
            if _monitor_instance is None:
                _monitor_instance = DPDKLiveMonitor(config, intances)
                _monitor_instance.start()
    return _monitor_instance


def shutdown_monitor():
    global _monitor_instance
    with _monitor_lock:
        if _monitor_instance is not None:
            _monitor_instance.stop()
            _monitor_instance = None
