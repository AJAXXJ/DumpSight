# ─────────────────────────────────────────────
# utils
# ─────────────────────────────────────────────


def _safe_get(d, path, default=None):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _delta(a, b):
    try:
        return float(b) - float(a)
    except Exception:
        return 0.0


def _window_seconds(samples):
    if len(samples) < 2:
        return 0.0
    try:
        return float(samples[-1]["timestamp"]) - float(samples[0]["timestamp"])
    except Exception:
        return 0.0


def _rate(delta, dt):
    return delta / dt if dt > 0 else 0.0


def _ratio(num, den):
    return num / den if den else 0.0


def _level(v, low, high):
    if v < low:
        return "low"
    if v < high:
        return "medium"
    return "high"


def _threshold_label(value, thresholds):
    """thresholds: [(threshold, label), ...] 升序"""
    for th, label in thresholds:
        if value < th:
            return label
    return thresholds[-1][1]


# ─────────────────────────────────────────────
# per-snapshot analyzers
# ─────────────────────────────────────────────


def _calc_queue_balance(q_ipackets):
    if not q_ipackets:
        return {
            "active_queues": 0,
            "total_packets": 0,
            "max_queue_packets": 0,
            "imbalance_ratio": 0.0,
        }
    total = sum(q_ipackets)
    max_q = max(q_ipackets)
    active = sum(1 for x in q_ipackets if x > 0)
    imbalance = _ratio(max_q, total) if active > 1 and total >= 100 else 0.0
    return {
        "active_queues": active,
        "total_packets": total,
        "max_queue_packets": max_q,
        "imbalance_ratio": imbalance,
    }


def _calc_mempool_stats(snapshot):
    result = {}
    for name, p in (snapshot.get("mempool_stats") or {}).items():
        size = float(p.get("size") or 0)
        common = float(p.get("common_pool_count") or 0)
        cache = float(p.get("total_cache_count") or 0)
        result[name] = {
            "name": p.get("name", name),
            "size": int(size),
            "populated_size": int(p.get("populated_size") or 0),
            "cache_size": int(p.get("cache_size") or 0),
            "elt_size": int(p.get("elt_size") or 0),
            "common_pool_count": int(common),
            "total_cache_count": int(cache),
            "free_ratio": _ratio(common, size),
            "cache_pressure": _ratio(cache, size),
        }
    return result


def _calc_heap_stats(snapshot):
    result = {}
    for hid, h in (snapshot.get("heap_stats") or {}).items():
        heap_size = float(h.get("Heap_size") or 0)
        free_size = float(h.get("Free_size") or 0)
        greatest = float(h.get("Greatest_free_size") or 0)
        result[hid] = {
            "name": h.get("Name", f"heap_{hid}"),
            "heap_size": int(heap_size),
            "free_size": int(free_size),
            "alloc_size": int(h.get("Alloc_size") or 0),
            "greatest_free_size": int(greatest),
            "alloc_count": int(h.get("Alloc_count") or 0),
            "free_count": int(h.get("Free_count") or 0),
            "free_ratio": _ratio(free_size, heap_size),
            "fragmentation": 1.0 - _ratio(greatest, free_size) if free_size else 0.0,
        }
    return result


def _calc_lcore_stats(snapshot):
    per_lcore = {}
    for group in (snapshot.get("lcore_usage") or {}).values():
        ids = group.get("lcore_ids") or []
        totals = group.get("total_cycles") or []
        busys = group.get("busy_cycles") or []
        ratios = group.get("usage_ratio") or []
        for i, lid in enumerate(ids):
            tc = totals[i] if i < len(totals) else 0
            bc = busys[i] if i < len(busys) else 0
            if tc == 0 and bc == 0:
                continue
            try:
                ur = float(str(ratios[i] if i < len(ratios) else "0").strip("%")) / 100
            except Exception:
                ur = 0.0
            if lid not in per_lcore or tc > per_lcore[lid]["total_cycles"]:
                per_lcore[lid] = {
                    "lcore_id": lid,
                    "usage_ratio": round(ur, 6),
                    "cycles_ratio": round(_ratio(bc, tc), 6),
                    "busy_cycles": bc,
                    "total_cycles": tc,
                }

    usages = [v["usage_ratio"] for v in per_lcore.values()]
    hottest = max(per_lcore, key=lambda k: per_lcore[k]["usage_ratio"], default=None)
    result = dict(per_lcore)
    result["__summary__"] = {
        "active_lcore_count": len(per_lcore),
        "avg_usage_all_lcores": round(_ratio(sum(usages), len(usages)), 6),
        "max_usage_all_lcores": round(max(usages), 6) if usages else 0.0,
        "hottest_lcore_id": hottest,
    }
    return result


# ─────────────────────────────────────────────
# port stats
# ─────────────────────────────────────────────


def _calc_port_stats(samples):
    if not samples:
        return {}
    first, last = samples[0], samples[-1]
    dt = _window_seconds(samples)

    result = {}
    for port_id in last.get("ethdev_stats") or last.get("ethdev_xstats") or {}:
        bs = _safe_get(last, ["ethdev_stats", port_id], {}) or {}
        bs0 = _safe_get(first, ["ethdev_stats", port_id], {}) or {}

        def bd(k):
            return (
                float(bs.get(k) or 0) - float(bs0.get(k) or 0)
                if bs0
                else float(bs.get(k) or 0)
            )

        rx_pkts = bd("ipackets")
        rx_bytes = bd("ibytes")
        tx_pkts = bd("opackets")
        tx_bytes = bd("obytes")
        ierr = bd("ierrors")
        oerr = bd("oerrors")
        nombuf = bd("rx_nombuf")

        xs = _safe_get(last, ["ethdev_xstats", port_id], {}) or {}
        xs0 = _safe_get(first, ["ethdev_xstats", port_id], {}) or {}

        def xd(k):
            return (
                float(xs.get(k) or 0) - float(xs0.get(k) or 0)
                if xs0
                else float(xs.get(k) or 0)
            )

        rx_good_pkts = xd("rx_good_packets")
        rx_missed = xd("rx_missed_errors")
        rx_err_x = xd("rx_errors")
        tx_err_x = xd("tx_errors")
        mbuf_err = xd("rx_mbuf_allocation_errors")
        multicast = xd("rx_q0_multicast_packets")
        broadcast = xd("rx_q0_broadcast_packets")
        undersize = xd("rx_q0_undersize_packets")

        link = _safe_get(last, ["ethdev_link", port_id], {}) or {}
        q_ip = bs.get("q_ipackets") or []
        q_ib = bs.get("q_ibytes") or []
        q_er = bs.get("q_errors") or []

        result[port_id] = {
            "link": {
                "status": link.get("status"),
                "speed": link.get("speed"),
                "duplex": link.get("duplex"),
            },
            "rx": {
                "packets_delta": int(rx_pkts),
                "bytes_delta": int(rx_bytes),
                "pps": _rate(rx_pkts, dt),
                "bps": _rate(rx_bytes * 8, dt),
                "avg_pkt_size": _ratio(rx_bytes, rx_pkts),
                "ierrors_delta": int(ierr),
                "rx_nombuf_delta": int(nombuf),
            },
            "tx": {
                "packets_delta": int(tx_pkts),
                "bytes_delta": int(tx_bytes),
                "pps": _rate(tx_pkts, dt),
                "bps": _rate(tx_bytes * 8, dt),
                "avg_pkt_size": _ratio(tx_bytes, tx_pkts),
                "oerrors_delta": int(oerr),
            },
            "queue": {
                "q_ipackets": q_ip,
                "q_ibytes": q_ib,
                "q_errors": q_er,
                **_calc_queue_balance(q_ip),
            },
            "traffic_pattern": {
                "rx_good_packets_delta": int(rx_good_pkts),
                "rx_missed_errors_delta": int(rx_missed),
                "rx_errors_delta": int(rx_err_x),
                "tx_errors_delta": int(tx_err_x),
                "rx_mbuf_alloc_errors_delta": int(mbuf_err),
                "multicast_packets_delta": int(multicast),
                "broadcast_packets_delta": int(broadcast),
                "undersize_packets_delta": int(undersize),
                "multicast_ratio": _ratio(multicast, rx_good_pkts),
                "broadcast_ratio": _ratio(broadcast, rx_good_pkts),
                "undersize_ratio": _ratio(undersize, rx_good_pkts),
            },
        }
    return result


# ─────────────────────────────────────────────
# build statistic
# ─────────────────────────────────────────────


def _build_statistic(samples):
    if not samples:
        return {
            "count": 0,
            "window_seconds": 0.0,
            "process": {},
            "ports": {},
            "mempool": {},
            "heap": {},
            "lcore": {},
        }
    first, last = samples[0], samples[-1]
    ws = _window_seconds(samples)
    return {
        "count": len(samples),
        "window_seconds": ws,
        "process": {
            "pid": last.get("pid"),
            "is_alive": last.get("is_alive"),
            "timestamp_start": first.get("timestamp"),
            "timestamp_end": last.get("timestamp"),
            "window_seconds": ws,
            "sample_count": len(samples),
            "type": last.get("type"),
        },
        "ports": _calc_port_stats(samples),
        "mempool": _calc_mempool_stats(last),
        "heap": _calc_heap_stats(last),
        "lcore": _calc_lcore_stats(last),
    }


def log_1s_statistic(metrics_1s):
    return _build_statistic(metrics_1s)


def log_5s_statistic(metrics_5s):
    return _build_statistic(metrics_5s)


# ─────────────────────────────────────────────
# trend / jitter helpers
# ─────────────────────────────────────────────


def _calc_jitter(values):
    if not values:
        return 0.0
    avg = _ratio(sum(values), len(values))
    if avg < 1.0:
        return 0.0
    variance = sum((x - avg) ** 2 for x in values) / len(values)
    return (variance**0.5) / avg


def _calc_short_trend(values):
    n = len(values)
    if n < 6:
        return "unknown"
    if max(values) < 5:
        return "stable"
    mid = n // 2
    avg_f = _ratio(sum(values[:mid]), mid)
    avg_l = _ratio(sum(values[mid:]), n - mid)
    if avg_f < 1e-6:
        return "unknown"
    r = avg_l / avg_f
    return "increasing_fast" if r > 1.2 else "decreasing_fast" if r < 0.8 else "stable"


def _extract_rx_pps_series(samples, max_dt=3.0):
    pps_list = []
    for i in range(1, len(samples)):
        prev, curr = samples[i - 1], samples[i]
        try:
            prev_ports = prev.get("ethdev_stats") or {}
            curr_ports = curr.get("ethdev_stats") or {}
            if not prev_ports or not curr_ports:
                continue
            port_id = max(curr_ports, key=lambda x: curr_ports[x].get("ipackets", 0))
            if port_id not in prev_ports:
                continue
            dt = float(curr.get("timestamp", 0)) - float(prev.get("timestamp", 0))
            if not (0.01 < dt <= max_dt):
                continue
            delta = max(
                curr_ports[port_id].get("ipackets", 0)
                - prev_ports[port_id].get("ipackets", 0),
                0,
            )
            pps = delta / dt
            if 0 <= pps <= 1e7:
                pps_list.append(pps)
        except Exception:
            continue

    alpha, smoothed = 0.3, []
    for v in pps_list:
        smoothed.append(v if not smoothed else alpha * v + (1 - alpha) * smoothed[-1])
    return smoothed


# ─────────────────────────────────────────────
# LLM feature builder
# ─────────────────────────────────────────────

_LOW_TRAFFIC_PPS = 10.0


def build_llm_features(statistic_1s, statistic_5s, metrics_1s):

    def _first_port(stat):
        return next(iter(stat.get("ports", {}).values()), {})

    def _first_pool(stat):
        return next(iter(stat.get("mempool", {}).values()), {})

    def _first_heap(stat):
        return next(iter(stat.get("heap", {}).values()), {})

    p1 = _first_port(statistic_1s)
    p5 = _first_port(statistic_5s)
    m1 = _first_pool(statistic_1s)
    m5 = _first_pool(statistic_5s)

    # cpu：优先5s（1s日志无lcore_usage）
    cpu5_sum = statistic_5s.get("lcore", {}).get("__summary__", {})
    cpu1_sum = statistic_1s.get("lcore", {}).get("__summary__", {})
    cpu_sum = (
        cpu5_sum
        if cpu5_sum.get("active_lcore_count", 0)
        >= cpu1_sum.get("active_lcore_count", 0)
        else cpu1_sum
    )

    # heap：优先5s（1s日志无heap_stats）
    heap = _first_heap(statistic_5s) or _first_heap(statistic_1s)

    # ── traffic ──
    rx_pps_1s = p1.get("rx", {}).get("pps", 0.0)
    tx_pps_1s = p1.get("tx", {}).get("pps", 0.0)
    traffic_level = _level(rx_pps_1s, 1e3, 1e6)

    # 5s维度pps：优先xstats，fallback ethdev_stats
    tp5 = p5.get("traffic_pattern", {})
    win5 = statistic_5s.get("window_seconds", 0.0)
    rx_good_5s = tp5.get("rx_good_packets_delta", 0)
    rx_pps_5s = (
        _rate(rx_good_5s, win5) if rx_good_5s > 0 else p5.get("rx", {}).get("pps", 0.0)
    )

    # pps序列 & 短期趋势
    pps_series = _extract_rx_pps_series(metrics_1s)
    if traffic_level == "low" and (
        not pps_series or max(pps_series, default=0) < _LOW_TRAFFIC_PPS
    ):
        rx_short_trend, rx_jitter = "stable", 0.0
    else:
        rx_jitter = _calc_jitter(pps_series)
        rx_short_trend = _calc_short_trend(pps_series)

    stability = (
        "stable"
        if traffic_level == "low"
        else (
            "unstable"
            if rx_jitter > 0.5
            else "slightly_unstable" if rx_jitter > 0.2 else "stable"
        )
    )

    # 长期趋势：低流量直接stable，避免噪声放大
    if rx_pps_1s < _LOW_TRAFFIC_PPS:
        traffic_trend = "stable"
    elif rx_pps_5s > 0:
        r = _ratio(rx_pps_1s + 1e-6, rx_pps_5s + 1e-6)
        traffic_trend = (
            "increasing" if r > 1.2 else "decreasing" if r < 0.8 else "stable"
        )
    else:
        traffic_trend = "unknown"

    avg_pkt = p1.get("rx", {}).get("avg_pkt_size", 0)
    pkt_type = "small" if avg_pkt < 128 else "large" if avg_pkt > 1000 else "normal"

    # ── queue ──
    imbalance = p1.get("queue", {}).get("imbalance_ratio", 0.0)
    queue_status = _threshold_label(
        imbalance, [(0.2, "balanced"), (0.5, "slight_skew"), (1.0, "severe_skew")]
    )

    # ── mempool ──
    mem = m1 if m1 else m5
    free_ratio = mem.get("free_ratio", 1.0)
    mem_status = _threshold_label(
        free_ratio, [(0.1, "critical"), (0.3, "warning"), (1.0, "healthy")]
    )
    r_mem = _ratio(free_ratio, (m5 or m1).get("free_ratio", free_ratio))
    mem_trend = (
        ("decreasing" if r_mem < 0.7 else "increasing" if r_mem > 1.3 else "stable")
        if r_mem
        else "unknown"
    )

    # ── heap ──
    heap_free = heap.get("free_ratio", 1.0)
    heap_frag = heap.get("fragmentation", 0.0)
    heap_status = _threshold_label(
        heap_free, [(0.05, "critical"), (0.15, "warning"), (1.0, "healthy")]
    )

    # ── cpu ──
    cpu_avg = cpu_sum.get("avg_usage_all_lcores", 0.0)
    cpu_status = _threshold_label(
        cpu_avg, [(0.3, "idle"), (0.7, "normal"), (1.0, "high")]
    )
    cpu_avg_1s = cpu1_sum.get("avg_usage_all_lcores", 0.0)
    cpu_avg_5s = cpu5_sum.get("avg_usage_all_lcores", cpu_avg)
    if cpu_avg_1s == 0.0 and cpu_avg_5s == 0.0:
        cpu_trend = "stable"
    elif cpu_avg_5s > 0:
        r = _ratio(cpu_avg_1s, cpu_avg_5s)
        cpu_trend = "increasing" if r > 1.2 else "decreasing" if r < 0.8 else "stable"
    else:
        cpu_trend = "unknown"

    # ── errors ──
    rx_err = p1.get("rx", {}).get("ierrors_delta", 0)
    tx_err = p1.get("tx", {}).get("oerrors_delta", 0)
    nombuf = p1.get("rx", {}).get("rx_nombuf_delta", 0)
    missed = p1.get("traffic_pattern", {}).get("rx_missed_errors_delta", 0)
    err_score = rx_err + tx_err + nombuf * 10 + missed * 5
    error_severity = _threshold_label(
        err_score, [(1, "none"), (10, "low"), (50, "medium"), (float("inf"), "high")]
    )

    traffic_safe = (
        error_severity == "none"
        and queue_status == "balanced"
        and mem_status == "healthy"
    )

    # ── insights（全部收集后统一判空）──
    insights = []
    if mem_status == "critical":
        insights.append("mempool nearly exhausted")
    if queue_status != "balanced":
        insights.append("queue imbalance detected")
    if cpu_status == "high":
        insights.append("cpu under high load")
    if error_severity in ("medium", "high"):
        insights.append("packet errors observed")
    if traffic_trend == "increasing":
        insights.append("traffic increasing rapidly")
    if mem_trend == "decreasing":
        insights.append("mempool decreasing rapidly")
    if cpu_trend == "increasing":
        insights.append("cpu load rising")
    if rx_short_trend == "increasing_fast":
        insights.append("traffic increasing sharply in short term")
    if rx_short_trend == "decreasing_fast" and len(pps_series) / 10 > 0.6:
        insights.append("traffic dropping rapidly")
    if stability == "unstable" and not traffic_safe:
        insights.append("traffic is highly unstable")
    if heap_status == "critical":
        insights.append("heap memory nearly exhausted")
    elif heap_status == "warning":
        insights.append("heap memory low")
    if heap_frag > 0.5:
        insights.append("heap memory heavily fragmented")
    if not insights:
        insights.append("system operating normally")
    if (
        traffic_level == "low"
        and error_severity == "none"
        and queue_status == "balanced"
        and "traffic is highly unstable" in insights
    ):
        insights.remove("traffic is highly unstable")

    # ── risks & score ──
    risks, rb = [], {}

    mem_s = (
        (50 if mem_status == "critical" else 20 if mem_status == "warning" else 0)
        + (30 if mem_trend == "decreasing" else 0)
        + min(nombuf * 10, 100)
    )
    if mem_s:
        rb["mempool"] = mem_s
    if mem_status == "critical" and mem_trend == "decreasing":
        risks.append("mempool_exhaustion_imminent")
    elif mem_status == "warning" and mem_trend == "decreasing":
        risks.append("mempool_exhaustion_risk")

    cpu_s = (30 if cpu_status == "high" else 0) + (
        20 if cpu_trend == "increasing" else 0
    )
    if cpu_s:
        rb["cpu"] = cpu_s
    if cpu_status == "high" and cpu_trend == "increasing":
        risks.append("cpu_overload_imminent")

    q_s = (
        20
        if queue_status == "severe_skew"
        else 10 if queue_status == "slight_skew" else 0
    )
    if q_s:
        rb["queue"] = q_s
    if queue_status == "severe_skew" and traffic_trend == "increasing":
        risks.append("queue_congestion_risk")

    t_s = (10 if traffic_trend == "increasing" else 0) + (
        10 if traffic_level == "high" else 0
    )
    if t_s:
        rb["traffic"] = t_s
    if nombuf > 0 and mem_status != "healthy":
        risks.append("packet_loss_due_to_mempool")
    if traffic_level == "high" and traffic_trend == "increasing":
        risks.append("traffic_surge")

    heap_s = (
        40 if heap_status == "critical" else 15 if heap_status == "warning" else 0
    ) + (10 if heap_frag > 0.5 else 0)
    if heap_s:
        rb["heap"] = heap_s
        if heap_status in ("critical", "warning"):
            risks.append("heap_memory_pressure")

    err_s = min(err_score, 100)
    if err_s:
        rb["errors"] = err_s

    risk_score = min(mem_s + cpu_s + q_s + t_s + heap_s + err_s, 100)
    risk_level = _threshold_label(
        risk_score, [(20, "low"), (50, "medium"), (80, "high"), (101, "critical")]
    )

    return {
        "window": {
            "1s": statistic_1s.get("window_seconds"),
            "5s": statistic_5s.get("window_seconds"),
        },
        "system_status": {
            "is_alive": statistic_1s.get("process", {}).get("is_alive")
            or statistic_5s.get("process", {}).get("is_alive")
            or False
        },
        "traffic": {
            "rx_pps": rx_pps_1s,
            "tx_pps": tx_pps_1s,
            "traffic_level": traffic_level,
            "trend": traffic_trend,
            "short_trend": rx_short_trend,
            "stability": stability,
            "packet_type": pkt_type,
        },
        "queue": {"imbalance_ratio": imbalance, "status": queue_status},
        "mempool": {"free_ratio": free_ratio, "status": mem_status, "trend": mem_trend},
        "heap": {
            "free_ratio": heap_free,
            "fragmentation": heap_frag,
            "status": heap_status,
        },
        "cpu": {
            "avg_usage": cpu_avg,
            "status": cpu_status,
            "trend": cpu_trend,
            "hot_lcore": cpu_sum.get("hottest_lcore_id"),
        },
        "errors": {
            "rx_errors": rx_err,
            "tx_errors": tx_err,
            "nombuf": nombuf,
            "missed": missed,
            "severity": error_severity,
        },
        "insight": insights,
        "risk": risks,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_breakdown": rb,
    }


# ─────────────────────────────────────────────
# reference feature builder
# ─────────────────────────────────────────────

# 参考窗口阈值倍率（当前值超出参考均值的倍率即触发预警）
_REF_ALERT_RATIO = {
    "rx_pps": 2.0,  # 当前pps > 参考均值2倍 → 流量突增
    "tx_pps": 2.0,
    "rx_errors": 1.0,  # 参考期有错误 → 只要当前>0即预警（倍率无意义时用绝对值）
    "tx_errors": 1.0,
    "queue_imbalance": 1.5,  # 队列倾斜度超参考1.5倍
    "cpu_avg": 1.5,  # CPU均值超参考1.5倍
}

_REF_ALERT_ABS = {
    # 绝对阈值：无论参考值多少，当前值超出即预警
    "rx_errors": 1,  # 任何接收错误
    "tx_errors": 1,
    "nombuf": 1,  # 任何MBUF不足
    "missed": 1,  # 任何丢包
    "mempool_free": 0.1,  # mempool空闲 < 10%（critical）
    "heap_free": 0.05,  # heap空闲 < 5%（critical）
}


def build_reference_features(
    reference_metrics_1s: list,
    reference_metrics_5s: list,
) -> dict:
    """
    基于 300s 历史窗口的 1s+5s 日志，计算参考基线特征。

    与 build_llm_features 保持相同的字段来源口径：
    - rx_pps / rx_errors / queue_imbalance / mempool_free：来自 1s 日志
    - heap_free / heap_frag / cpu_avg / cpu_max：          来自 5s 日志

    Args:
        reference_metrics_1s: 历史 1s 日志列表（约300条）
        reference_metrics_5s: 历史 5s 日志列表（约60条）

    Returns:
        与 _FEATURE_PATH_MAP 键名对齐的基线特征字典
    """
    stat_1s = log_1s_statistic(reference_metrics_1s) if reference_metrics_1s else {}
    stat_5s = log_5s_statistic(reference_metrics_5s) if reference_metrics_5s else {}

    def _first_port(s): return next(iter(s.get("ports",   {}).values()), {})
    def _first_pool(s): return next(iter(s.get("mempool", {}).values()), {})
    def _first_heap(s): return next(iter(s.get("heap",    {}).values()), {})

    # 1s 日志字段
    p1 = _first_port(stat_1s)
    m1 = _first_pool(stat_1s)

    # 5s 日志字段
    p5  = _first_port(stat_5s)
    h5  = _first_heap(stat_5s)
    cpu = stat_5s.get("lcore", {}).get("__summary__", {})

    return {
        # 来自 1s 日志
        "rx_pps":          p1.get("rx", {}).get("pps", 0.0),
        "tx_pps":          p1.get("tx", {}).get("pps", 0.0),
        "rx_errors":       p1.get("rx", {}).get("ierrors_delta", 0),
        "tx_errors":       p1.get("tx", {}).get("oerrors_delta", 0),
        "nombuf":          p1.get("rx", {}).get("rx_nombuf_delta", 0),
        "missed":          p1.get("traffic_pattern", {}).get("rx_missed_errors_delta", 0),
        "queue_imbalance": p1.get("queue", {}).get("imbalance_ratio", 0.0),
        "mempool_free":    m1.get("free_ratio", 1.0),
        # 来自 5s 日志（口径与 log_feature 对齐）
        "heap_free":       h5.get("free_ratio",    1.0),
        "heap_frag":       h5.get("fragmentation", 0.0),
        "cpu_avg":         cpu.get("avg_usage_all_lcores", 0.0),
        "cpu_max":         cpu.get("max_usage_all_lcores", 0.0),
        # 元信息
        "window_seconds":  stat_1s.get("window_seconds", 0.0),
        "sample_count":    stat_1s.get("count", 0),
    }
