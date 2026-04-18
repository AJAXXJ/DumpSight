import threading
import logging
import time

from agent.graphs.live_monitor.graph import (
    get_realtime_monitor_graph,
    run_fast_poll,
    run_slow_poll,
)
from agent.graphs.live_monitor.nodes import cleanup_clients
from server.repository.client_redis import get_client_running_instances
from server.service.client_service import client_get_all_alive_info

logger = logging.getLogger(__name__)


def start_client_monitor(
    client_id: str,
    pid: int,
    alert_handler=None,
    fault_handler=None,
    fast_interval: int = 10,
    slow_interval: int = 60,
) -> dict[str, threading.Thread]:
    """
    为单个客户端启动双频监控线程。

    快速线程（fast_interval=10s）：只跑规则引擎，低延迟捕捉确定性异常。
    慢速线程（slow_interval=60s）：规则+语义，捕捉规则盲区和趋势异常。

    两个线程均为 daemon 线程，主进程退出时自动终止。
    通过返回的 stop_event 可以优雅停止指定客户端的监控。

    Args:
        client_id:      客户端标识
        pid:            DPDK 进程 PID
        alert_handler:  告警回调
        fault_handler:  故障升级回调
        fast_interval:  快速轮询间隔（秒），默认 10s
        slow_interval:  慢速轮询间隔（秒），默认 60s

    Returns:
        {
            "stop_event":   threading.Event,   # 调用 .set() 停止该客户端所有线程
            "fast_thread":  threading.Thread,
            "slow_thread":  threading.Thread,
        }
    """

    graph = get_realtime_monitor_graph()
    stop_event = threading.Event()

    def _fast_loop():
        logger.info(
            "fast_poll loop started | client=%s pid=%s interval=%ss",
            client_id,
            pid,
            fast_interval,
        )
        while not stop_event.is_set():
            try:
                run_fast_poll(graph, client_id, pid, alert_handler, fault_handler)
            except Exception as e:
                logger.exception("fast_poll loop error | client=%s | %s", client_id, e)
            stop_event.wait(timeout=fast_interval)
        logger.info("fast_poll loop stopped | client=%s", client_id)

    def _slow_loop():
        logger.info(
            "slow_poll loop started | client=%s pid=%s interval=%ss",
            client_id,
            pid,
            slow_interval,
        )
        while not stop_event.is_set():
            try:
                run_slow_poll(graph, client_id, pid, alert_handler, fault_handler)
            except Exception as e:
                logger.exception("slow_poll loop error | client=%s | %s", client_id, e)
            stop_event.wait(timeout=slow_interval)
        logger.info("slow_poll loop stopped | client=%s", client_id)

    fast_thread = threading.Thread(
        target=_fast_loop,
        daemon=True,
        name=f"fast_poll:{client_id}:{pid}",
    )
    slow_thread = threading.Thread(
        target=_slow_loop,
        daemon=True,
        name=f"slow_poll:{client_id}:{pid}",
    )

    fast_thread.start()
    slow_thread.start()

    return {
        "stop_event": stop_event,
        "fast_thread": fast_thread,
        "slow_thread": slow_thread,
    }


def stop_client_monitor(monitor_handle: dict):
    """
    优雅停止指定客户端的监控线程。

    Args:
        monitor_handle: start_client_monitor 返回的 dict
    """
    stop_event = monitor_handle.get("stop_event")
    if stop_event:
        stop_event.set()

    for key in ("fast_thread", "slow_thread"):
        t = monitor_handle.get(key)
        if t and t.is_alive():
            t.join(timeout=5)
            if t.is_alive():
                logger.warning("thread did not stop in time | thread=%s", t.name)


# 全局监控句柄注册表，key: "client_id:pid"
_monitor_registry: dict[str, dict] = {}


def register_client_monitor(
    client_id: str,
    pid: int,
    alert_handler=None,
    fault_handler=None,
    fast_interval: int = 10,
    slow_interval: int = 60,
):
    """
    注册并启动客户端监控，已注册的客户端跳过重复注册。

    Args:
        client_id:     客户端标识
        pid:           DPDK 进程 PID
        alert_handler: 告警回调
        fault_handler: 故障升级回调
        fast_interval: 快速轮询间隔（秒）
        slow_interval: 慢速轮询间隔（秒）
    """
    key = f"{client_id}:{pid}"
    if key in _monitor_registry:
        logger.info("client already monitored, skip | client=%s pid=%s", client_id, pid)
        return

    handle = start_client_monitor(
        client_id=client_id,
        pid=pid,
        alert_handler=alert_handler,
        fault_handler=fault_handler,
        fast_interval=fast_interval,
        slow_interval=slow_interval,
    )
    _monitor_registry[key] = handle
    logger.info("client monitor registered | client=%s pid=%s", client_id, pid)


def unregister_client_monitor(client_id: str, pid: int):
    """
    停止并注销客户端监控，同时清理冷却缓存。

    Args:
        client_id: 客户端标识
        pid:       DPDK 进程 PID
    """

    key = f"{client_id}:{pid}"
    handle = _monitor_registry.pop(key, None)
    if handle:
        stop_client_monitor(handle)
        logger.info("client monitor unregistered | client=%s pid=%s", client_id, pid)
    else:
        logger.warning(
            "client not found in registry | client=%s pid=%s", client_id, pid
        )

    cleanup_clients([client_id])


def unregister_all_monitors():
    """停止并注销所有客户端监控，通常在服务关闭时调用。"""

    keys = list(_monitor_registry.keys())
    client_ids = list({k.split(":")[0] for k in keys})

    for key in keys:
        handle = _monitor_registry.pop(key, None)
        if handle:
            stop_client_monitor(handle)

    cleanup_clients(client_ids)
    logger.info("all client monitors unregistered | total=%d", len(keys))


def sync_client_monitors(
    alert_handler=None,
    fault_handler=None,
    fast_interval: int = 10,
    slow_interval: int = 60,
    sync_interval: int = 30,
):
    """
    定时同步客户端监控注册表，自动注册新实例、注销已停止实例。

    同步逻辑：
        1. 从数据库拉取所有已注册客户端
        2. 对每个客户端拉取当前 running 实例列表
        3. running 实例不在注册表中 → 自动注册启动监控
        4. 注册表中的实例不再 running  → 自动注销停止监控

    Args:
        alert_handler:  告警回调，透传给 register_client_monitor
        fault_handler:  故障升级回调，透传给 register_client_monitor
        fast_interval:  快速轮询间隔（秒）
        slow_interval:  慢速轮询间隔（秒）
        sync_interval:  同步检查间隔（秒），默认 30s
    """

    logger.info("sync_client_monitors started | sync_interval=%ss", sync_interval)

    while True:
        try:
            _do_sync(
                alert_handler=alert_handler,
                fault_handler=fault_handler,
                fast_interval=fast_interval,
                slow_interval=slow_interval,
            )
        except Exception as e:
            logger.exception("sync_client_monitors error | %s", e)

        time.sleep(sync_interval)


def _do_sync(
    alert_handler=None,
    fault_handler=None,
    fast_interval: int = 10,
    slow_interval: int = 60,
):
    """
    执行一次同步：对比数据库 running 实例与当前注册表，补全注册和注销。
    """
    # 当前注册表中所有 key（"client_id:pid"）
    registered_keys = set(_monitor_registry.keys())

    # 数据库中所有 running 实例的 key
    running_keys: set[str] = set()

    clients = client_get_all_alive_info()
    for client in clients:
        client_id = client.get("client_id")
        if not client_id:
            continue

        try:
            instances = get_client_running_instances(client_id) or []
        except Exception as e:
            logger.warning(
                "get_client_running_instances failed | client=%s | %s", client_id, e
            )
            continue

        for instance in instances:
            pid = instance.get("pid")
            if not pid:
                continue
            running_keys.add(f"{client_id}:{pid}")

    # 新增：running 但未注册
    to_register = running_keys - registered_keys
    for key in to_register:
        client_id, pid = key.split(":", 1)
        logger.info("sync: registering new instance | client=%s pid=%s", client_id, pid)
        register_client_monitor(
            client_id=client_id,
            pid=int(pid),
            alert_handler=alert_handler,
            fault_handler=fault_handler,
            fast_interval=fast_interval,
            slow_interval=slow_interval,
        )

    # 移除：已注册但不再 running
    to_unregister = registered_keys - running_keys
    for key in to_unregister:
        client_id, pid = key.split(":", 1)
        logger.info(
            "sync: unregistering stopped instance | client=%s pid=%s", client_id, pid
        )
        unregister_client_monitor(client_id=client_id, pid=int(pid))

    if to_register or to_unregister:
        logger.info(
            "sync done | registered=%d unregistered=%d active=%d",
            len(to_register),
            len(to_unregister),
            len(_monitor_registry),
        )
    else:
        logger.debug("sync done | no changes | active=%d", len(_monitor_registry))


def start_sync_thread(
    alert_handler=None,
    fault_handler=None,
    fast_interval: int = 10,
    slow_interval: int = 60,
    sync_interval: int = 30,
) -> threading.Thread:
    """
    在后台线程中启动定时同步，返回线程对象。

    Args:
        alert_handler:  告警回调
        fault_handler:  故障升级回调
        fast_interval:  快速轮询间隔（秒）
        slow_interval:  慢速轮询间隔（秒）
        sync_interval:  同步检查间隔（秒），默认 30s

    Returns:
        daemon 同步线程，主进程退出时自动终止
    """
    t = threading.Thread(
        target=sync_client_monitors,
        kwargs={
            "alert_handler": alert_handler,
            "fault_handler": fault_handler,
            "fast_interval": fast_interval,
            "slow_interval": slow_interval,
            "sync_interval": sync_interval,
        },
        daemon=True,
        name="client_monitor_sync",
    )
    t.start()
    logger.info("sync thread started | sync_interval=%ss", sync_interval)
    return t
