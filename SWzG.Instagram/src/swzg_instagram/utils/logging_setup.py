from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


def setup_logging(
    syslog_dir: Path,
    errors_dir: Path,
    actions_dir: Path,
    log_level: str = "INFO",
) -> None:
    syslog_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)
    actions_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S%z"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplication
    root.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(console)

    # Syslog file handler
    sys_handler = logging.FileHandler(syslog_dir / f"syslog_{ts}.log", encoding="utf-8")
    sys_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    sys_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(sys_handler)

    # Error file handler
    err_handler = logging.FileHandler(errors_dir / f"errors_{ts}.log", encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(err_handler)

    # Actions file handler
    act_handler = logging.FileHandler(actions_dir / f"actions_{ts}.log", encoding="utf-8")
    act_handler.setLevel(logging.DEBUG)
    act_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    act_logger = logging.getLogger("actions")
    act_logger.handlers.clear()
    act_logger.addHandler(act_handler)
    act_logger.setLevel(logging.DEBUG)
    act_logger.propagate = True
