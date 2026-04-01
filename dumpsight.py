import os
import sys
import click
import subprocess

from config import DumpSightConfig
from tools.utils import UniqueIDGenerator, check_root
from tools.logger import logger

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

    try:
        subprocess.run(
            ["tee", "/proc/sys/kernel/core_pattern"],
            input=pattern, text=True, check=True
        )
        click.echo(f"Core pattern configured via tee: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by tee: {e}", err=True)

    try:
        subprocess.run(
            ["sysctl", "-w", f"kernel.core_pattern={pattern}"],
            check=True, capture_output=True
        )
        click.echo(f"Core pattern configured via sysctl: {pattern}")
        return
    except Exception as e:
        click.echo(f"Failed to configure core_pattern by sysctl: {e}", err=True)
 
    sys.exit(1)


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

    # Run the DPDK app and redirect output to the specified log file
    try:
        cmd_str = " ".join(cmd)
        log = os.path.join(config.logs_dir, log)
        subprocess.run(f"{cmd_str} > {log} 2>&1", shell=True, check=True)
        click.echo(f"DPDK running command executed successfully. ELA log is redirected to {log}")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running dpdk app: {e}", err=True)

    # TODO 记录日志和监控DPDK应用的性能指标



cli.add_command(setup)
cli.add_command(monitor)

if __name__ == '__main__':
    cli()