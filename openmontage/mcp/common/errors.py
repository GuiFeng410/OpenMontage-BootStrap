"""MCP error types."""

from __future__ import annotations

from lib.error_codes import CONFIG_ERROR, DOCTOR_ERROR, SANDBOX_VIOLATION


class DoctorError(Exception):
    """Base error for doctor MCP tools."""

    def __init__(self, message: str, *, code: str = DOCTOR_ERROR) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SandboxError(DoctorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=SANDBOX_VIOLATION)


class ConfigError(DoctorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=CONFIG_ERROR)
