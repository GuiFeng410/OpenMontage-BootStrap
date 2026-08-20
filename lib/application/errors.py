"""Domain errors for application use cases. MCP maps these to DoctorError."""


class ApplicationError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
