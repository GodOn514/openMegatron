import logging
import os
from pathlib import Path


def configure_module_logger(
    name: str,
    log_file_name: str,
    console_level: str = None,
    file_level: str = "INFO",
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_dir = Path(__file__).resolve().parent.parent / "log"
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(log_dir / log_file_name, encoding="utf-8")
    file_handler.setLevel(_level(file_level, logging.INFO))
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)

    resolved_console_level = console_level or os.environ.get("MEGATRON_CONSOLE_LOG_LEVEL", "WARNING")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_level(resolved_console_level, logging.WARNING))
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    return logger


def _level(value: str, default: int) -> int:
    if isinstance(value, int):
        return value
    return getattr(logging, str(value or "").upper(), default)
