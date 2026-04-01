import os
import sys
import time
import click
import threading
from tools.logger import logger

def check_root():
    """
    检查是否以 root 权限运行
    """
    if os.geteuid() != 0:
        click.echo("This command must be run as root.", err=True)
        sys.exit(1)


class UniqueIDGenerator:
    """
    A simple unique ID generator that creates unique IDs based on timestamp and sequence.
    """

    def __init__(self):
        self.sequence = 0
        self.lock = threading.Lock()

    def generate_unique_id(self):
        with self.lock:
            timestamp = int(time.time() * 1000)
            self.sequence += 1
            return f"{timestamp}{self.sequence}"