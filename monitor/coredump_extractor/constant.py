# 信号值表
SIGNAL_MAP = {
    6: "SIGABRT",
    11: "SIGSEGV",
    8: "SIGFPE",
    4: "SIGILL"
}

# 正常等待状态 线程直接跳过不记录
IDLE_FRAMES = {
    "read ()",
    "epoll_wait ()",
    "pthread_cond_wait ()",
    "pthread_cond_timedwait ()",
    "futex_wait ()",
    "nanosleep ()",
    "clock_nanosleep ()",
}

# DPDK 子系统
SUBSYSTEMS = {
        "mempool": r"rte_mempool|rte_pktmbuf",
        "ring":    r"rte_ring",
        "eal":     r"rte_eal|eal_",
        "ethdev":  r"rte_eth|rte_dev",
        "mbuf":    r"rte_mbuf",
        "malloc":  r"rte_malloc|malloc_elem",
}

# 关键寄存器
KEY_REGISTER = ["rip", "rsp", "rbp", "rdi", "rsi", "rdx"]

# 关键 DPDK 库名
CRITICAL_DPDK_LIBS = [
    "librte_eal",
    "librte_mbuf",
    "librte_ethdev",
    "librte_mempool",
    "librte_ring",
    "librte_pci",
    "librte_bus_pci",
    "librte_bus_vdev",
    "librte_kvargs",
    "librte_telemetry",
]

KEY_LS_CPU = [
            "Architecture",
            "CPU(s)",
            "Socket(s)",
            "Core(s) per socket",
            "Thread(s) per core",
            "NUMA node(s)",
            "NUMA node0 CPU(s)",
            "NUMA node1 CPU(s)",
            "Vendor ID",
            "Model name",
            "CPU max MHz",
            "CPU min MHz"
        ]

# 统一超时/采集配置
GDB_TIMEOUT = 60
COLLECT_TIMEOUT = 5
FILE_STABLE_TIMEOUT = 5
APP_LOG_TAIL_LINES = 200