import logging
import os
import time
from datetime import datetime

import colorlog


_LOG_COLORS = {
    "DEBUG":    "white",
    "INFO":     "white",
    "WARNING":  "yellow",
    "ERROR":    "red",
    "CRITICAL": "bold_red",
}

_COLOR_FMT = "%(log_color)s%(asctime)s [%(levelname)-5s]%(reset)s %(name)s — %(message)s"
_PLAIN_FMT = "%(asctime)s [%(levelname)-5s] %(name)s — %(message)s"


class _UTCFormatter(logging.Formatter):
    """Plain formatter with ISO 8601 UTC timestamps. Used for log files."""
    converter = time.gmtime

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{t}.{int(record.msecs):03d}Z"


class _UTCColorFormatter(colorlog.ColoredFormatter):
    """Colored formatter with ISO 8601 UTC timestamps. Used for console output."""
    converter = time.gmtime

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{t}.{int(record.msecs):03d}Z"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console — colored output
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(_UTCColorFormatter(_COLOR_FMT, log_colors=_LOG_COLORS))
    logger.addHandler(console)

    # File — plain text, no ANSI codes
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, f"run_{datetime.utcnow().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_UTCFormatter(_PLAIN_FMT))
    logger.addHandler(file_handler)

    return logger
