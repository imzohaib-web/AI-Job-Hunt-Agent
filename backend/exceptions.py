"""
backend/exceptions.py
-------------------
Domain exceptions mapped to HTTP responses in main.py.
"""


class APIError(Exception):
    """Base API error with HTTP status code and message."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(APIError):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class NotFoundError(APIError):
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


class AgentProcessingError(APIError):
    """Raised when an agent pipeline step fails."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500)
