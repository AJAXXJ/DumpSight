import sys
import click
import subprocess
import threading

from tools.events import monitor_core

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

def run_daemon(config):
    """
    Runs the DumpSight monitor in daemon mode.
    """
    threads = [
        threading.Thread(target=monitor_core, args=(config,), name="monitor", daemon=True),
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join()