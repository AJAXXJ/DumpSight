import os
import time
import click
import psutil
import subprocess
from pathlib import Path
from config import config
from monitor.monitor_manager import get_monitor_manager
from monitor.request import client_register, client_status
from tools.daemon import install_systemd_service, run_daemon, systemctl
from tools.utils import check_root, id_generator


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
            input=pattern,
            text=True,
            check=True,
        )
        click.echo(f"Core pattern configured via tee: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by tee: {e}", err=True)

    # sysctl
    try:
        subprocess.run(
            ["sysctl", "-w", f"kernel.core_pattern={pattern}"],
            check=True,
            capture_output=True,
        )
        click.echo(f"Core pattern configured via sysctl: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by sysctl: {e}", err=True)


@click.command()
@click.option(
    "--client_id", prompt="Enter Client ID", help="The client ID for DumpSight. "
)
@click.option(
    "--client_secret", prompt="Enter Client Secret", help="The secret for the client. "
)
@click.option(
    "--server_url", prompt="Enter Server URL", help="The server URL for DumpSight. "
)
@click.option(
    "--redis_host", prompt="Enter Redis Host", help="The Redis Host for DumpSight. "
)
@click.option(
    "--redis_port", prompt="Enter Redis Port", help="The Redis Port for DumpSight. "
)
@click.option(
    "--redis_db",
    prompt="Enter Redis DB Number",
    help="The Redis DB Number for DumpSight. ",
)
@click.option(
    "--redis_password",
    prompt="Enter Redis Password",
    help="The Redis Password for DumpSight. ",
)
def setup(
    client_id,
    client_secret,
    server_url,
    redis_host,
    redis_port,
    redis_db,
    redis_password,
):
    """
    Setup DumpSight environment.
    """
    check_root()

    # configure global config
    config.set_config("client_id", client_id)
    config.set_config("client_secret", client_secret)

    config.set_config("server_url", server_url)

    config.set_config("redis_host", redis_host)
    config.set_config("redis_port", redis_port)
    config.set_config("redis_db", redis_db)
    config.set_config("redis_password", redis_password)

    # register client to server
    # try:
    #     client_register(config)
    # except Exception as e:
    #     click.echo(f"Client registration failed: {e}", err=True)
    #     return

    # configure core pattern
    pattern = f"{config.core_dump_dir}/core.%e.%p.%i.%s.%t.%E"
    _configure_core_pattern(pattern)

    # configure daemon systemd service
    install_systemd_service()

    click.echo("Client registration successful.")


@click.command()
def status():
    """
    Check the status of DumpSight.
    """
    if getattr(config, "server_url", None) is None:
        click.echo("DumpSight is not setup yet.")
        return
    
    # core_pattern status
    try:
        with open("/proc/sys/kernel/core_pattern") as f:
            pattern = f.read().strip()
        click.echo(f"Current core_pattern: {pattern}")
    except Exception as e:
        click.echo(f"Unable to read core_pattern: {e}", err=True)

    # daemon status
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "dumpsight"], check=True, capture_output=True
        )
        daemon_status = result.stdout.decode().strip()
        click.echo(f"DumpSight daemon status: {daemon_status}")
    except subprocess.CalledProcessError as e:
        click.echo(f"DumpSight daemon is not active: {e}", err=True)
        click.echo("You can setup using 'dumpsight setup' command.")

    # config status
    click.echo("Current DumpSight configuration:")

    # client registration status
    # try:
    #     client_status(config)
    #     click.echo("Client already registered with the server.")
    # except Exception as e:
    #     click.echo(f"Client status check failed: {e}", err=True)


@click.command(
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    )
)
@click.argument("dpdk_running_args", nargs=-1)
@click.option(
    "--file_prefix",
    default=None,
    help="The prefix for the dpdk app file.",
)
@click.option(
    "--instance",
    default=None,
    help="The instance name for the dpdk app.",
)
@click.option(
    "--log",
    default=None,
    help="Log file to redirect output.",
)
def monitor(dpdk_running_args, file_prefix, instance, log):
    """
    Monitor DPDK apps.
    """
    cmd = list(dpdk_running_args)

    # Run the DPDK app and redirect output to the specified log file
    try:
        cmd_str = " ".join(cmd)
        if log is None:
            log = f"dpdk_{id_generator.generate_unique_id()}.log"
        log = os.path.join(config.logs_dir, log)

        if file_prefix:
            cmd_str = f"{cmd_str} --file-prefix={file_prefix}"

        if instance:
            cmd_str = f"{cmd_str} --instance={instance}"
        
        process = subprocess.Popen(f"{cmd_str} > {log} 2>&1", shell=True)

        click.echo(
            f"DPDK running command executed successfully. ELA log is redirected to {log}"
        )
    except (OSError, FileNotFoundError) as e:
        click.echo(f"Error running dpdk app: {e}", err=True)
        return

    # exe path
    dpdk_app_path = cmd[0]
    if not Path(dpdk_app_path).is_absolute():
        dpdk_app_path = str(Path(dpdk_app_path).resolve())

    # exe pid
    children = psutil.Process(process.pid).children(recursive=True)
    pid = children[0].pid if children else process.pid

    monitor_info = {
        "cmd": cmd_str,
        "exe_name": Path(dpdk_app_path).name,
        "exe_path": dpdk_app_path,
        "file_prefix": file_prefix,
        "instance": instance,
        "log_path": log,
        "status": "running",
        "start_time": time.time(),
    }

    # Save monitor info to the monitor file
    get_monitor_manager().add_monitor_info(pid, monitor_info)


@click.command()
def daemon():
    """
    Run DumpSight monitor in daemon mode.
    """
    run_daemon(config)


@click.command()
def daemon_start():
    """
    Start the DumpSight daemon.
    """
    systemctl("start")


@click.command()
def daemon_stop():
    """
    Stop the DumpSight daemon.
    """
    systemctl("stop")


@click.command()
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


if __name__ == "__main__":
    cli()
