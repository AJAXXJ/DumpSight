# 信号值表
SIGNAL_MAP = {
    4:  "SIGILL",
    6:  "SIGABRT",
    7:  "SIGBUS",   # 总线错误，常见于非对齐内存访问
    8:  "SIGFPE",
    11: "SIGSEGV",
    13: "SIGPIPE",  # 写入已关闭的管道
    15: "SIGTERM",  # 正常终止
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

_GDB_COMMANDS = [
    "set print frame-arguments all",
    "echo === INFO_THREADS_BEGIN ===\\n",
    "info threads",
    "echo === INFO_THREADS_END ===\\n",
    "echo === THREAD_BT_BEGIN ===\\n",
    "thread apply all bt 5",
    "echo === THREAD_BT_END ===\\n",
    "echo === BT_FULL_BEGIN ===\\n",
    "bt full",
    "echo === BT_FULL_END ===\\n",
    "echo === REGISTERS_BEGIN ===\\n",
    "info registers",
    "echo === REGISTERS_END ===\\n",
    "echo === RSP_BEGIN ===\\n",
    "x/4xg $rsp",
    "echo === RSP_END ===\\n",
    "echo === RBP_BEGIN ===\\n",
    "x/4xg $rbp",
    "echo === RBP_END ===\\n",
    "echo === SHARED_BEGIN ===\\n",
    "info shared",
    "echo === SHARED_END ===\\n",
    "echo === ARGS_BEGIN ===\\n",
    "show args",
    "echo === ARGS_END ===\\n",
    "echo === MAPPINGS_BEGIN ===\\n",
    "info proc mappings",
    "echo === MAPPINGS_END ===\\n",
]



# 统一超时/采集配置
APP_LOG_INIT_LINES = 500
APP_LOG_TAIL_LINES = 200
GDB_TIMEOUT = 60
COLLECT_TIMEOUT = 5
FILE_STABLE_TIMEOUT = 5
APP_LOG_TAIL_LINES = 200