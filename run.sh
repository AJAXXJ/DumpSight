# setup
python dumpsight.py setup
# monitor DPDK app
python dumpsight.py monitor  /home/crash/dpdk_crash --no-huge -m 64 --vdev net_null0

./dpdk_crash --no-huge -m 64 --vdev net_null0

./dumpsight monitor  ../test/dpdk_crash --no-huge -m 64 --vdev net_null0
# package
pyinstaller --onefile dumpsight.py 