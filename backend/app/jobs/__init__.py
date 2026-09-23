"""Background job layer.

Local mode uses :class:`app.jobs.in_process.InProcessDispatcher` (no Redis).
Production runs the arq worker defined in :mod:`app.jobs.worker`.
"""

from __future__ import annotations

from app.jobs.handlers import (
    EmbeddingJob,
    GoalProgressJob,
    MemoryAnalysisJob,
    MemoryCompactionJob,
)
from app.jobs.in_process import REGISTRY, InProcessDispatcher, dispatcher

__all__ = [
    "REGISTRY",
    "EmbeddingJob",
    "GoalProgressJob",
    "InProcessDispatcher",
    "MemoryAnalysisJob",
    "MemoryCompactionJob",
    "dispatcher",
]
