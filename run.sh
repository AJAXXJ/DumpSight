# setup
python dumpsight.py setup

# monitor DPDK app
python dumpsight.py daemon-restart 

# live
python dumpsight.py monitor "/workspace/test/dpdk_live -l 0-1 -n 4" --file_prefix=dpdk_live
./dumpsight monitor "/workspace/test/dpdk_live -l 0-1 -n 4 --proc-type=primary" --file_prefix=dpdk_live

# simple_crash
python dumpsight.py monitor "/workspace/test/dpdk_crash -l 0-1 -n 4" --file_prefix=dpdk_crash
./dumpsight monitor "/workspace/test/dpdk_crash -l 0-1 -n 4" --file_prefix=dpdk_crash

# complex_crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_complex -l 0,1,2 -n 4" --file_prefix=dpdk_crash_complex
./dumpsight monitor "/workspace/test/dpdk_crash_complex -l 0,1,2 -n 4" --file_prefix=dpdk_crash_complex

# OOM crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_oom -l 0 -n 4" --file_prefix=dpdk_crash_oom
./dumpsight monitor "/workspace/test/dpdk_crash_oom -l 0 -n 4" --file_prefix=dpdk_crash_oom

# package
pyinstaller --onefile dumpsight.py 

journalctl -u dumpsight.service -f

ulimit -c unlimited