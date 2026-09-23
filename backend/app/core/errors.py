from __future__ import annotations

import enum


class ErrorCode(str, enum.Enum):
    AUTH_UNAUTHORIZED = "AUTH_UNAUTHORIZED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    GOAL_NOT_FOUND = "GOAL_NOT_FOUND"
    JOURNAL_NOT_FOUND = "JOURNAL_NOT_FOUND"
    MEMORY_NOT_FOUND = "MEMORY_NOT_FOUND"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_PERMISSION_DENIED = "TOOL_PERMISSION_DENIED"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"
    LLM_ERROR = "LLM_ERROR"
    VECTOR_SEARCH_ERROR = "VECTOR_SEARCH_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(code, message, status_code=404)


class PermissionDeniedError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(ErrorCode.TOOL_PERMISSION_DENIED, message, status_code=403)
