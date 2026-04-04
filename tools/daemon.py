import signal
import sys
import click
import subprocess
import threading
from monitor.live_monitor import DPDKLiveMonitor
from monitor.monitor_utils import read_monitor_list, read_monitor_list_by_status
from monitor.request import client_heartbeat
from tools.events import clean_crashed_core, monitor_core, send_client_heartbeat

SERVICE_PATH = "/etc/systemd/system/dumpsight.service"

SERVICE_CONTENT = """\
[Unit]
Description=DumpSight Core Monitor
After=network.target

[Service]
ExecStart={exec_start}
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""

def install_systemd_service():
    """
    Installs the DumpSight systemd service to run the monitor in the background.
    """
    exec_start = f"{sys.executable} daemon"
    
    with open(SERVICE_PATH, 'w') as f:
        f.write(SERVICE_CONTENT.format(exec_start=exec_start))
    click.echo(f"Service file written to {SERVICE_PATH}")

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "dumpsight"], check=True)
    subprocess.run(["systemctl", "start", "dumpsight"], check=True)
    click.echo("DumpSight service enabled and started.")

def systemctl(action):
    """
    Helper function to control the DumpSight systemd service.
    """
    subprocess.run(["systemctl", action, "dumpsight"], check=True)


def read_running_instances_info(monitor_file):
    """
    Read information about running DPDK instances from the monitor file.
    """
    instances = []
    running_apps_info = read_monitor_list_by_status(monitor_file, status="running")
    for pid, info in running_apps_info:
        instances.append({
            "pid": pid,
            "exe_name": info.get("exe_name"),
            "exe_path": info.get("exe_path"),
            "file_prefix": info.get("file_prefix"),
            "instance": info.get("instance"),
        })
    return instances

def run_daemon(config):
    """
    Runs the DumpSight monitor in daemon mode.
    """
    # Initialize the DPDK monitor with the current running instances
    dpdk_monitor = DPDKLiveMonitor(
        config=config,
        instances=read_running_instances_info(config.monitor_file),
    )
    dpdk_monitor.start()

    threads = [
        threading.Thread(target=monitor_core, args=(config,), name="monitor", daemon=True),
        threading.Thread(target=clean_crashed_core, args=(config,), name="clean", daemon=True),
        threading.Thread(target=send_client_heartbeat, args=(config, dpdk_monitor), name="heartbeat", daemon=True),
    ]

    for t in threads:
        t.start()
    
    for t in threads:
        t.join()

    dpdk_monitor.stop()
    client_heartbeat(config, batch=dpdk_monitor.flush())