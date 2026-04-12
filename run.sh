# setup
python dumpsight.py setup
# monitor DPDK app
./dumpsight monitor "../test/dpdk_test -l 0-1 -n 4 --no-pci"
./dumpsight monitor "../test/dpdk_crash -l 0-1 -n 4 --no-pci"

# package
pyinstaller --onefile dumpsight.py 

pyinstaller --onefile main.py

./dumpsight monitor "../test/dpdk_live -l 0-1 -n 4 --vdev=net_tap0 --proc-type=primary"
