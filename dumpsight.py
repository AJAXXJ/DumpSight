import os
import click
import subprocess
from config import DumpSightConfig
from monitor.monitor_utils import add_monitor_info
from tools.daemon_utils import install_systemd_service, run_daemon, systemctl
from tools.utils import UniqueIDGenerator, check_root

config = DumpSightConfig()
id_generator = UniqueIDGenerator()

@click.group()
def cli():
    """DumpSight CLI Tool"""
    pass

@click.command()
def setup():
    """
    Setup DumpSight environment.
    """
    check_root()
    pattern = f"{config.core_dump_dir}/core.%e.%p.%i.%s.%t.%E"

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
    print(cmd)
    # Run the DPDK app and redirect output to the specified log file
    try:
        cmd_str = " ".join(cmd)
        log = os.path.join(config.logs_dir, log)
        subprocess.run(f"{cmd_str} > {log} 2>&1", shell=True, check=True)
        click.echo(f"DPDK running command executed successfully. ELA log is redirected to {log}")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running dpdk app: {e}", err=True)

    # exe path
    dpdk_app_path = cmd[0]
    # exe pid
    pid = subprocess.check_output(f"pgrep -f '{dpdk_app_path}'", shell=True).decode().strip()
    

    monitor_info = {
        "exe_path": dpdk_app_path,
        "log_path": log,
        "status": "running"
    }

    # Save monitor info to the monitor file
    add_monitor_info(config.monitor_file, pid, monitor_info)


@cli.command()
@click.pass_context
def daemon(ctx):
    config = ctx.obj
    run_daemon(config)

@cli.command()
def daemon_start():
    systemctl("start")

@cli.command()
def daemon_stop():
    systemctl("stop")

@cli.command()
def daemon_restart():
    systemctl("restart")


cli.add_command(setup)
cli.add_command(status)
cli.add_command(monitor)
cli.add_command(daemon_start)
cli.add_command(daemon_stop)
cli.add_command(daemon_restart)


if __name__ == '__main__':
    cli()