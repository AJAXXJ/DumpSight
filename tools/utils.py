import inspect
import os
import sys
import time
import click
import threading
from tools.logger import logger

def check_root():
    """
    Check if the current user is root.
    """
    if os.geteuid() != 0:
        click.echo("This command must be run as root.", err=True)
        sys.exit(1)

def timer(func):
    """
    Decorator to measure the execution time of a function.
    """
    def wrapper(*args, **kwargs):
        bound = inspect.signature(func).bind(*args, **kwargs)
        bound.apply_defaults()
        filename = bound.arguments.get("filename", None)

        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        
        logger.info(f"{func.__name__} 分析 {filename} 耗时: {end - start:.6f} 秒")
        return result
    return wrapper

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