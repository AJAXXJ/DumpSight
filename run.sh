# setup
python dumpsight.py setup

# monitor DPDK app
./dumpsight monitor "/workspace/test/dpdk_live -l 0-1 -n 4 --file-prefix=dpdk_live"

./dumpsight monitor "/workspace/test/dpdk_crash -l 0-1 -n 4 --file-prefix=dpdk_crash"

# package
pyinstaller --onefile dumpsight.py 

pyinstaller --onefile main.py

./dumpsight monitor "../test/dpdk_live -l 0-1 -n 4 --vdev=net_tap0 --proc-type=primary"

journalctl -u dumpsight.service -f