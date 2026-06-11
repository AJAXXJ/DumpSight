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
./dumpsight monitor "/workspace/test/dpdk_crash_25_11_1 -l 0-1 -n 4" --file_prefix=dpdk_crash_25_11_1
./dumpsight monitor "/workspace/test/dpdk_crash_24_11_5 -l 0-1 -n 4" --file_prefix=dpdk_crash_24_11_5
./dumpsight monitor "/workspace/test/dpdk_crash_22_11_11 -l 0-1 -n 4" --file_prefix=dpdk_crash_22_11_11
./dumpsight monitor "/workspace/test/dpdk_crash_21_11_9 -l 0-1 -n 4" --file_prefix=dpdk_crash_21_11_9
./dumpsight monitor "/workspace/test/dpdk_crash_20_11_10 -l 0-1 -n 4" --file_prefix=dpdk_crash_20_11_10
./dumpsight monitor "/workspace/test/dpdk_crash_19_11_14 -l 0-1 -n 4" --file_prefix=dpdk_crash_19_11_14

# complex_crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_complex -l 0,1,2 -n 4" --file_prefix=dpdk_crash_complex
./dumpsight monitor "/workspace/test/dpdk_crash_complex -l 0,1,2 -n 4" --file_prefix=dpdk_crash_complex

# OOM crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_oom -l 0 -n 4" --file_prefix=dpdk_crash_oom
./dumpsight monitor "/workspace/test/dpdk_crash_oom -l 0 -n 4" --file_prefix=dpdk_crash_oom

# big crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_big -l 0 -n 4" --file_prefix=dpdk_crash_big
./dumpsight monitor "/workspace/test/dpdk_crash_big -l 0 -n 4" --file_prefix=dpdk_crash_big

# mid crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_mid -l 0 -n 4" --file_prefix=dpdk_crash_mid
./dumpsight monitor "/workspace/test/dpdk_crash_mid -l 0 -n 4" --file_prefix=dpdk_crash_mid

# huge crash
python dumpsight.py monitor "/workspace/test/dpdk_crash_huge -l 0 -n 4" --file_prefix=dpdk_crash_huge
./dumpsight monitor "/workspace/test/dpdk_crash_huge -l 0 -n 4" --file_prefix=dpdk_crash_huge
# package
pyinstaller --onefile dumpsight.py 

journalctl -u dumpsight.service -f

ulimit -c unlimited