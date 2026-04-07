# setup
python dumpsight.py setup
# monitor DPDK app
python dumpsight.py monitor  /home/crash/dpdk_crash --no-huge -m 64 --vdev net_null0

./dpdk_crash --no-huge -m 64 --vdev net_null0

./dumpsight monitor  ../test/dpdk_crash --no-huge -m 64 --vdev net_null0
# package
pyinstaller --onefile dumpsight.py 

./build/app/dpdk-testpmd -l 0-1 -n 4 --no-pci -- -i --total-num-mbufs 1025


python dumpsight.py monitor "../dpdk/dpdk-stable-23.11.6/build/app/dpdk-testpmd -l 0-1 -n 4 --no-pci -- --total-num-mbufs 1025"