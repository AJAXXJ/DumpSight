import logging
import sys

def setup_logger(log_file=None, level=logging.INFO):
    """
    setup_logger initializes the logging configuration for the application.
    """
    logger = logging.getLogger()
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        handlers.append(file_handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

logger = setup_logger("DumpSight_running.log", logging.DEBUG)
logging.getLogger("schedule").setLevel(logging.INFO)