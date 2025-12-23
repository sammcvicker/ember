"""Tests for use case error handling utilities."""

import logging

import pytest

from ember.core.use_case_errors import (
    EmberError,
    format_error_message,
    log_use_case_error,
)


class TestEmberError:
    """Tests for EmberError base exception class."""

    def test_message_stored_on_exception(self) -> None:
        """EmberError stores the message attribute."""
        error = EmberError("Test error message")
        assert error.message == "Test error message"

    def test_message_used_as_str(self) -> None:
        """EmberError message is used for str()."""
        error = EmberError("Test error message")
        assert str(error) == "Test error message"

    def test_can_be_raised_and_caught(self) -> None:
        """EmberError can be raised and caught as Exception."""
        with pytest.raises(EmberError) as exc_info:
            raise EmberError("Test error")
        assert exc_info.value.message == "Test error"


class TestFormatErrorMessage:
    """Tests for format_error_message utility function."""

    def test_ember_error_uses_message_directly(self) -> None:
        """EmberError subclasses use their message directly."""
        error = EmberError("User-friendly message")
        result = format_error_message(error, "operation")
        assert result == "User-friendly message"

    def test_oserror_adds_context(self) -> None:
        """OSError gets additional context about permissions/disk space."""
        error = OSError("Permission denied")
        result = format_error_message(error, "indexing")
        assert "I/O error: Permission denied" in result
        assert "permissions" in result
        assert "disk space" in result

    def test_valueerror_includes_operation_name(self) -> None:
        """ValueError includes the operation name in the message."""
        error = ValueError("Invalid value")
        result = format_error_message(error, "validation")
        assert "Validation error: Invalid value" in result

    def test_runtimeerror_includes_operation_name(self) -> None:
        """RuntimeError includes the operation name in the message."""
        error = RuntimeError("Something went wrong")
        result = format_error_message(error, "processing")
        assert "Processing error: Something went wrong" in result

    def test_generic_exception_returns_internal_error(self) -> None:
        """Unknown exceptions return a generic internal error message."""
        error = TypeError("type error details")
        result = format_error_message(error, "indexing")
        assert "Internal error during indexing" in result
        assert "type error details" not in result  # Don't expose internals

    def test_operation_name_capitalized(self) -> None:
        """Operation name is capitalized in error messages."""
        error = ValueError("test")
        result = format_error_message(error, "status check")
        assert "Status check error" in result


class TestLogUseCaseError:
    """Tests for log_use_case_error utility function."""

    def test_ember_error_logged_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """EmberError is logged at ERROR level."""
        error = EmberError("Domain error")
        with caplog.at_level(logging.ERROR):
            log_use_case_error(error, "operation")
        assert "Domain error" in caplog.text

    def test_oserror_logged_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """OSError is logged at ERROR level with operation context."""
        error = OSError("Permission denied")
        with caplog.at_level(logging.ERROR):
            log_use_case_error(error, "indexing")
        assert "I/O error during indexing" in caplog.text
        assert "Permission denied" in caplog.text

    def test_valueerror_logged_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ValueError is logged at ERROR level."""
        error = ValueError("Invalid value")
        with caplog.at_level(logging.ERROR):
            log_use_case_error(error, "validation")
        assert "validation" in caplog.text
        assert "Invalid value" in caplog.text

    def test_runtimeerror_logged_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """RuntimeError is logged at ERROR level."""
        error = RuntimeError("Runtime issue")
        with caplog.at_level(logging.ERROR):
            log_use_case_error(error, "processing")
        assert "processing" in caplog.text
        assert "Runtime issue" in caplog.text

    def test_generic_exception_logged_with_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unknown exceptions are logged with traceback (exception level)."""
        error = TypeError("unexpected type")
        with caplog.at_level(logging.ERROR):
            log_use_case_error(error, "indexing")
        assert "Unexpected error during indexing" in caplog.text


class TestEmberErrorSubclass:
    """Tests for creating EmberError subclasses."""

    def test_custom_subclass_works_with_format(self) -> None:
        """Custom EmberError subclasses work with format_error_message."""

        class CustomError(EmberError):
            def __init__(self, detail: str) -> None:
                super().__init__(f"Custom: {detail}")
                self.detail = detail

        error = CustomError("specific detail")
        result = format_error_message(error, "operation")
        assert result == "Custom: specific detail"

    def test_custom_subclass_preserves_attributes(self) -> None:
        """Custom EmberError subclasses can have additional attributes."""

        class DetailedError(EmberError):
            def __init__(self, message: str, code: int) -> None:
                super().__init__(message)
                self.code = code

        error = DetailedError("Error with code", code=42)
        assert error.message == "Error with code"
        assert error.code == 42
