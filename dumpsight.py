import os
import click
import resource
import subprocess
from pathlib import Path
from config import DumpSightConfig
from monitor.monitor_utils import add_monitor_info
from tools.daemon import install_systemd_service, run_daemon, systemctl
from tools.utils import UniqueIDGenerator, check_root

config = DumpSightConfig()
id_generator = UniqueIDGenerator()

@click.group()
def cli():
    """DumpSight CLI Tool"""
    pass


def _configure_core_pattern(pattern):
    """
    Configure the core pattern for core dumps.
    """
    # tee
    try:
        subprocess.run(
            ["tee", "/proc/sys/kernel/core_pattern"],
            input=pattern, text=True, check=True
        )
        click.echo(f"Core pattern configured via tee: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by tee: {e}", err=True)

    # sysctl
    try:
        subprocess.run(
            ["sysctl", "-w", f"kernel.core_pattern={pattern}"],
            check=True, capture_output=True
        )
        click.echo(f"Core pattern configured via sysctl: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by sysctl: {e}", err=True)

@click.command()
def setup():
    """
    Setup DumpSight environment.
    """
    check_root()
    # configure core pattern
    pattern = f"{config.core_dump_dir}/core.%e.%p.%i.%s.%t.%E"
    _configure_core_pattern(pattern)
 
    # configure daemon systemd service
    install_systemd_service()

@click.command()
def status():
    """
    Check the status of DumpSight.
    """
    # core_pattern status
    try:
        with open("/proc/sys/kernel/core_pattern") as f:
            pattern = f.read().strip()
        click.echo(f"Current core_pattern: {pattern}")
    except Exception as e:
        click.echo(f"Unable to read core_pattern: {e}", err=True)

    # daemon status
    try:
        result = subprocess.run(["systemctl", "is-active", "dumpsight"], check=True, capture_output=True)
        status = result.stdout.decode().strip()
        click.echo(f"DumpSight daemon status: {status}")
    except subprocess.CalledProcessError as e:
        click.echo(f"DumpSight daemon is not active: {e}", err=True)
        click.echo("You can setup using 'dumpsight setup' command.")


    

@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.argument('dpdk_running_args', nargs=-1)
@click.option('--log', default=f'dpdk_{id_generator.generate_unique_id()}.log', help="Log file to redirect output.")
def monitor(dpdk_running_args, log):
    """
    Monitor DPDK apps.
    """
    cmd = list(dpdk_running_args)
    def set_core_dump():
        resource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
    # Run the DPDK app and redirect output to the specified log file
    try:
        cmd_str = " ".join(cmd)
        log = os.path.join(config.logs_dir, log)

        process = subprocess.Popen(f"{cmd_str} > {log} 2>&1", shell=True)

        click.echo(f"DPDK running command executed successfully. ELA log is redirected to {log}")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running dpdk app: {e}", err=True)

    # exe path
    dpdk_app_path =  cmd[0]
    if not Path(dpdk_app_path).is_absolute():
        dpdk_app_path = str(Path(dpdk_app_path).resolve())
    # exe pid
    pid = process.pid + 1

    monitor_info = {
        "exe_path": dpdk_app_path,
        "log_path": log,
        "status": "running"
    }

    # Save monitor info to the monitor file
    add_monitor_info(config.monitor_file, pid, monitor_info)


@cli.command()
def daemon():
    """
    Run DumpSight monitor in daemon mode.
    """
    run_daemon(config)

@cli.command()
def daemon_start():
    """
    Start the DumpSight daemon.
    """
    systemctl("start")

@cli.command()
def daemon_stop():
    """
    Stop the DumpSight daemon.
    """
    systemctl("stop")

@cli.command()
def daemon_restart():
    """
    Restart the DumpSight daemon.
    """
    systemctl("restart")


cli.add_command(setup)
cli.add_command(status)
cli.add_command(monitor)
cli.add_command(daemon_start)
cli.add_command(daemon_stop)
cli.add_command(daemon_restart)


if __name__ == '__main__':
    cli()