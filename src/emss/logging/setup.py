from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


class RedactingFilter(logging.Filter):
    _patterns = (
        re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*[^\s,;]+"),
        re.compile(r"(?i)(secret|token|api[_-]?key)\s*[=:]\s*[^\s,;]+"),
        re.compile(r"(?i)(mysql(?:\+pymysql)?://[^:\s]+:)[^@\s]+@"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(r"\1=[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    redactor = RedactingFilter()

    file_handler = RotatingFileHandler(
        log_dir / "emss.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redactor)

    root.addHandler(file_handler)
    root.addHandler(console_handler)

