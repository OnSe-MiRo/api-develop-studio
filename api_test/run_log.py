from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .runner import CaseConfigurationError


def create_run_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    """Create one UTF-8 file logger for an API test pipeline invocation."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CaseConfigurationError(f"Cannot create log directory {log_dir}: {exc}") from exc

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"api-test_{timestamp}.log"
    logger = logging.getLogger(f"api_test.run.{timestamp}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger, log_path
