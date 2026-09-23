from __future__ import annotations

import logging

import structlog

_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.JSONRenderer(),
]

structlog.configure(processors=_processors, wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

logger = structlog.get_logger("personalos")
