"""MCP error types."""

from __future__ import annotations


class DoctorError(Exception):
    """Base error for doctor MCP tools."""

    def __init__(self, message: str, *, code: str = "doctor_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SandboxError(DoctorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="sandbox_violation")


class ConfigError(DoctorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="config_error")
