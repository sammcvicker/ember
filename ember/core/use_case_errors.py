"""Use case error handling utilities.

Provides consistent exception handling across all use cases. All use cases
should return error responses rather than raising exceptions (except for
KeyboardInterrupt/SystemExit).

Design principles:
1. KeyboardInterrupt and SystemExit are always re-raised (never caught)
2. EmberError subclasses are domain errors with user-friendly messages
3. Unexpected exceptions are logged and converted to generic error messages
4. All use cases return responses with success/error fields

Error handling contract:
    Use cases catch exceptions internally and return error responses.
    This provides a consistent API for callers - they check response.success
    rather than catching multiple exception types.
"""

import logging

logger = logging.getLogger(__name__)


class EmberError(Exception):
    """Base exception for all ember domain errors.

    Subclass this for specific error types. The error message should be
    user-friendly since it may be displayed directly to users.

    Attributes:
        message: User-friendly error message.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def format_error_message(exception: Exception, operation_name: str) -> str:
    """Format an exception into a user-friendly error message.

    This function provides consistent error message formatting across all
    use cases. It handles different exception types appropriately:
    - EmberError: Uses the error's message directly
    - OSError: Adds context about permissions/disk space
    - ValueError/RuntimeError: Includes exception message with operation context
    - Other exceptions: Returns a generic "internal error" message

    Args:
        exception: The exception that was caught.
        operation_name: Name of the operation for error messages (e.g., "indexing").

    Returns:
        User-friendly error message string.

    Example:
        try:
            result = self._do_work()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            error_msg = format_error_message(e, "indexing")
            return self._create_error_response(error_msg)
    """
    if isinstance(exception, EmberError):
        return exception.message
    elif isinstance(exception, OSError):
        return (
            f"I/O error: {exception}. "
            "Check file permissions, disk space, and filesystem access."
        )
    elif isinstance(exception, (ValueError, RuntimeError)):
        return f"{operation_name.capitalize()} error: {exception}"
    else:
        return f"Internal error during {operation_name}. Check logs for details."


def log_use_case_error(exception: Exception, operation_name: str) -> None:
    """Log an exception from a use case with appropriate severity.

    This function provides consistent error logging across all use cases.
    It uses appropriate log levels based on exception type:
    - EmberError: ERROR level (expected domain errors)
    - OSError/ValueError/RuntimeError: ERROR level
    - Other exceptions: EXCEPTION level (includes traceback)

    Args:
        exception: The exception that was caught.
        operation_name: Name of the operation for log messages.
    """
    if isinstance(exception, EmberError):
        logger.error(str(exception))
    elif isinstance(exception, OSError):
        logger.error(f"I/O error during {operation_name}: {exception}")
    elif isinstance(exception, (ValueError, RuntimeError)):
        logger.error(f"Error during {operation_name}: {exception}")
    else:
        logger.exception(f"Unexpected error during {operation_name}")
