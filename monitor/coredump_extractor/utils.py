import os
import sys
import time
import subprocess
import click


def check_root():
    """
    检查是否以 root 权限运行
    """
    if os.geteuid() != 0:
        click.echo("This command must be run as root.", err=True)
        sys.exit(1)


def safe_run(cmd, timeout=5):
    """
    安全执行命令，失败时返回与 subprocess.run 兼容的轻量结果对象
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        class _R:
            returncode = 127
            stdout = ""
            stderr = f"{cmd[0]} not found"
        return _R()
    except subprocess.TimeoutExpired as exc:
        class _R:
            returncode = 124
            stdout = exc.stdout or ""
            stderr = (exc.stderr or "") + "\ncommand timeout"
        return _R()


def safe_read_text(path, encoding="utf-8", errors="ignore"):
    """
    安全读取文本，失败返回 None
    """
    try:
        with open(path, "r", encoding=encoding, errors=errors) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def wait_file_stable(path, timeout=30, interval=0.5):
    """
    等待文件写入稳定（连续两次大小一致且>0）
    """
    prev_size = -1
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(0.2)
            continue
        if size == prev_size and size > 0:
            return True
        prev_size = size
        time.sleep(interval)
    return False


def parse_pid_from_filename(filename):
    """
    从 core.<exe>.<pid>... 文件名中解析 pid，失败返回 None
    """
    try:
        parts = filename.split(".")
        return int(parts[2])
    except (IndexError, ValueError):
        return None


def is_probable_executable(path):
    """
    粗略判断是否为可执行文件（x 位或 ELF 头）
    """
    if not os.path.isfile(path):
        return False

    if os.access(path, os.X_OK):
        return True

    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False