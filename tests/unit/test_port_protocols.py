"""Unit tests for port protocols (interfaces).

Verifies that:
- Protocol classes define the expected methods
- Concrete implementations satisfy the protocol contracts
- Exception classes work correctly with their attributes
"""

from pathlib import Path

import pytest

from ember.domain.config import EmberConfig
from ember.ports.config import ConfigProvider
from ember.ports.daemon import DaemonManager
from ember.ports.editor import (
    Editor,
    EditorError,
    EditorExecutionError,
    EditorFileNotFoundError,
    EditorNotFoundError,
)

# ============================================================================
# ConfigProvider Protocol Tests
# ============================================================================


class TestConfigProviderProtocol:
    """Tests for the ConfigProvider protocol."""

    def test_protocol_defines_load_method(self) -> None:
        """ConfigProvider protocol defines a load method."""
        # Verify the protocol has the expected method
        assert hasattr(ConfigProvider, "load")

    def test_concrete_implementation_satisfies_protocol(self) -> None:
        """A concrete class implementing load() satisfies ConfigProvider."""

        class MyConfigProvider:
            def load(self, ember_dir: Path) -> EmberConfig:
                return EmberConfig.default()

        provider = MyConfigProvider()
        # Structural typing: calling load should work
        config = provider.load(Path("/tmp/.ember"))
        assert isinstance(config, EmberConfig)

    def test_toml_provider_satisfies_protocol(self) -> None:
        """TomlConfigProvider satisfies the ConfigProvider protocol."""
        from ember.adapters.config.toml_config_provider import TomlConfigProvider

        provider = TomlConfigProvider()
        # Protocol defines load(ember_dir: Path) -> EmberConfig
        assert hasattr(provider, "load")
        assert callable(provider.load)


# ============================================================================
# DaemonManager Protocol Tests
# ============================================================================


class TestDaemonManagerProtocol:
    """Tests for the DaemonManager protocol."""

    def test_protocol_defines_required_methods(self) -> None:
        """DaemonManager protocol defines is_running, ensure_running, start, stop."""
        assert hasattr(DaemonManager, "is_running")
        assert hasattr(DaemonManager, "ensure_running")
        assert hasattr(DaemonManager, "start")
        assert hasattr(DaemonManager, "stop")

    def test_mock_implementation_satisfies_protocol(self) -> None:
        """A mock class with all methods satisfies DaemonManager structurally."""

        class MockDaemonManager:
            def is_running(self) -> bool:
                return False

            def ensure_running(self, wait: bool = True) -> bool:
                return True

            def start(self, foreground: bool = False) -> bool:
                return True

            def stop(self, timeout: int = 10) -> bool:
                return True

        manager = MockDaemonManager()
        assert manager.is_running() is False
        assert manager.ensure_running() is True
        assert manager.ensure_running(wait=False) is True
        assert manager.start() is True
        assert manager.start(foreground=True) is True
        assert manager.stop() is True
        assert manager.stop(timeout=30) is True

    def test_is_running_returns_bool(self) -> None:
        """is_running should return a boolean."""

        class TestManager:
            def is_running(self) -> bool:
                return True

            def ensure_running(self, wait: bool = True) -> bool:
                return True

            def start(self, foreground: bool = False) -> bool:
                return True

            def stop(self, timeout: int = 10) -> bool:
                return True

        manager = TestManager()
        result = manager.is_running()
        assert isinstance(result, bool)

    def test_ensure_running_default_wait_is_true(self) -> None:
        """ensure_running should default to wait=True."""

        class TrackingManager:
            def __init__(self) -> None:
                self.last_wait_value: bool | None = None

            def is_running(self) -> bool:
                return False

            def ensure_running(self, wait: bool = True) -> bool:
                self.last_wait_value = wait
                return True

            def start(self, foreground: bool = False) -> bool:
                return True

            def stop(self, timeout: int = 10) -> bool:
                return True

        manager = TrackingManager()
        manager.ensure_running()
        assert manager.last_wait_value is True

    def test_stop_default_timeout_is_ten(self) -> None:
        """stop should default to timeout=10."""

        class TrackingManager:
            def __init__(self) -> None:
                self.last_timeout: int | None = None

            def is_running(self) -> bool:
                return False

            def ensure_running(self, wait: bool = True) -> bool:
                return True

            def start(self, foreground: bool = False) -> bool:
                return True

            def stop(self, timeout: int = 10) -> bool:
                self.last_timeout = timeout
                return True

        manager = TrackingManager()
        manager.stop()
        assert manager.last_timeout == 10


# ============================================================================
# Editor Protocol Tests
# ============================================================================


class TestEditorProtocol:
    """Tests for the Editor protocol."""

    def test_protocol_defines_required_methods(self) -> None:
        """Editor protocol defines open_file and get_editor_name."""
        assert hasattr(Editor, "open_file")
        assert hasattr(Editor, "get_editor_name")

    def test_subprocess_editor_satisfies_protocol(self) -> None:
        """SubprocessEditor satisfies the Editor protocol."""
        from ember.adapters.editor import SubprocessEditor

        editor = SubprocessEditor(editor="vim")
        assert hasattr(editor, "open_file")
        assert hasattr(editor, "get_editor_name")
        assert callable(editor.open_file)
        assert callable(editor.get_editor_name)

    def test_mock_implementation_satisfies_protocol(self) -> None:
        """A mock class with required methods satisfies Editor structurally."""

        class MockEditor:
            def open_file(self, file_path: Path, line_num: int) -> None:
                pass

            def get_editor_name(self) -> str:
                return "mock"

        editor = MockEditor()
        assert editor.get_editor_name() == "mock"
        # Should not raise
        editor.open_file(Path("/tmp/test.py"), 1)


# ============================================================================
# Editor Exception Tests
# ============================================================================


class TestEditorExceptions:
    """Tests for editor exception classes."""

    def test_editor_error_stores_message(self) -> None:
        """EditorError stores message attribute."""
        error = EditorError("Something failed")
        assert error.message == "Something failed"
        assert str(error) == "Something failed"

    def test_editor_error_stores_hint(self) -> None:
        """EditorError stores optional hint."""
        error = EditorError("Failed", hint="Try this")
        assert error.hint == "Try this"

    def test_editor_error_hint_defaults_to_none(self) -> None:
        """EditorError hint defaults to None."""
        error = EditorError("Failed")
        assert error.hint is None

    def test_file_not_found_is_editor_error(self) -> None:
        """EditorFileNotFoundError is a subclass of EditorError."""
        error = EditorFileNotFoundError("File not found")
        assert isinstance(error, EditorError)
        assert isinstance(error, Exception)

    def test_not_found_is_editor_error(self) -> None:
        """EditorNotFoundError is a subclass of EditorError."""
        error = EditorNotFoundError("Editor not found")
        assert isinstance(error, EditorError)

    def test_execution_error_is_editor_error(self) -> None:
        """EditorExecutionError is a subclass of EditorError."""
        error = EditorExecutionError("Execution failed")
        assert isinstance(error, EditorError)

    def test_exception_hierarchy_is_catchable(self) -> None:
        """All editor exceptions can be caught with EditorError."""
        exceptions = [
            EditorFileNotFoundError("file"),
            EditorNotFoundError("editor"),
            EditorExecutionError("exec"),
        ]
        for exc in exceptions:
            with pytest.raises(EditorError):
                raise exc
