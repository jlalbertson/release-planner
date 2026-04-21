"""Logging configuration: text format for CLI, JSON for production web server."""

from __future__ import annotations

import json
import logging
import sys


def configure_logging(*, json_format: bool = False, level: str = "INFO") -> None:
    """Configure logging for CLI (text) or web server (JSON).

    Args:
        json_format: If True, emit JSON lines for log aggregation.
            Auto-enabled when RELEASE_PLANNER_LOG_FORMAT=json.
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(log_level)


class _JsonFormatter(logging.Formatter):
    """Format log records as JSON lines for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)
