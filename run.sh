# setup
python dumpsight.py setup

# monitor DPDK app
python dumpsight.py daemon-restart 

python dumpsight.py monitor "/workspace/test/dpdk_live -l 0-1 -n 4" --file_prefix=dpdk_live
./dumpsight monitor "/workspace/test/dpdk_live -l 0-1 -n 4 --proc-type=primary" --file_prefix=dpdk_live

python dumpsight.py monitor "/workspace/test/dpdk_crash -l 0-1 -n 4" --file_prefix=dpdk_crash
./dumpsight monitor "/workspace/test/dpdk_crash -l 0-1 -n 4" --file_prefix=dpdk_crash
# package
pyinstaller --onefile dumpsight.py 

journalctl -u dumpsight.service -f