# 初始化
python dumpsight.py setup
# 接管 DPDK app
python dumpsight.py monitor  /home/crash/dpdk_crash --no-huge -m 64 --vdev net_null0