from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any

import structlog

from app.core.config import settings

# uvicorn's loggers install their own handlers, so a handler on the root logger
# would never see an access line. Only these two are chain *roots* — both carry
# ``propagate=False``. ``uvicorn.error`` is deliberately absent: it propagates
# into ``uvicorn``, so attaching there too would write every startup line twice.
#
# Not covered: the reloader *parent* process (``--reload``) never imports this
# module, so its three lines — "Will watch for changes in these directories",
# "Uvicorn running on ...", "Started reloader process [n]" — stay on the console
# only. The worker's own startup block is what lands in the file.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access")

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "exception": logging.ERROR,
    "critical": logging.CRITICAL,
    "fatal": logging.CRITICAL,
}


def _build_file_handler() -> logging.Handler | None:
    """Open the rotating log file, or return None when file logging is off."""
    if not settings.log_file:
        return None
    path = Path(settings.log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    # structlog lines arrive already rendered as JSON, uvicorn's as bare messages;
    # "%(message)s" adds no decoration of its own, so each logger's content lands
    # in the file unmodified. The console still differs in *presentation* — uvicorn
    # prefixes its own lines with "INFO:     " and may colour them — but the
    # message itself is identical, so the two streams can never disagree about
    # what happened.
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


_file_handler = _build_file_handler()


def _mirror_to_file(logger: Any, method_name: str, rendered: str) -> str:
    """Copy a fully rendered structlog line into the file handler.

    Sits *after* ``JSONRenderer`` in the chain, so ``rendered`` is the exact
    string stdout is about to receive rather than a re-serialisation of it.
    """
    if _file_handler is not None:
        _file_handler.emit(
            logging.LogRecord(
                name="personalos",
                level=_LEVELS.get(method_name, logging.INFO),
                pathname="",
                lineno=0,
                msg=rendered,
                args=None,
                exc_info=None,
            )
        )
    return rendered


_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.JSONRenderer(),
    _mirror_to_file,
]

structlog.configure(processors=_processors, wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

if _file_handler is not None:
    for _name in _UVICORN_LOGGERS:
        logging.getLogger(_name).addHandler(_file_handler)

logger = structlog.get_logger("personalos")
