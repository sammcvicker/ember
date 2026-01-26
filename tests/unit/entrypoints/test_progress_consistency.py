"""Unit tests for progress bar consistency across commands.

Issue #417: Progress bar inconsistencies across commands
"""

from unittest.mock import MagicMock, patch

import pytest

from ember.entrypoints.cli import (
    _ensure_model_downloaded,
    _show_interactive_sync_message,
    _show_sync_completion_message,
)


class TestModelDownloadProgress:
    """Tests for model download progress bar."""

    def test_returns_true_immediately_when_cached(self) -> None:
        """Should return True immediately when model is already cached."""
        with patch(
            "ember.adapters.local_models.is_model_cached", return_value=True
        ) as mock_cached:
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is True
            mock_cached.assert_called_once_with("jina-code-v2")

    def test_downloads_model_when_not_cached(self) -> None:
        """Should download model and return True when not cached."""
        mock_embedder = MagicMock()
        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is True
            mock_embedder.ensure_loaded.assert_called_once()

    def test_downloads_in_quiet_mode(self) -> None:
        """Should download model without progress bar in quiet mode."""
        mock_embedder = MagicMock()
        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=True)

            assert result is True
            mock_embedder.ensure_loaded.assert_called_once()

    def test_quiet_mode_suppresses_output(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should suppress progress output in quiet mode on success."""
        mock_embedder = MagicMock()
        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            _ensure_model_downloaded("jina-code-v2", quiet=True)

            captured = capsys.readouterr()
            # Quiet mode should not show "Downloading" messages
            assert "Downloading" not in captured.out
            assert "Downloaded" not in captured.out


class TestInteractiveSyncMessage:
    """Tests for interactive sync message respecting quiet mode."""

    def test_shows_message_in_interactive_mode_without_progress(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show sync message in interactive mode without progress bar."""
        _show_interactive_sync_message(
            interactive_mode=True,
            show_progress=False,
            quiet=False,
        )

        captured = capsys.readouterr()
        assert "Syncing" in captured.err

    def test_no_message_when_progress_bar_shown(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should not show message when progress bar is already being shown."""
        _show_interactive_sync_message(
            interactive_mode=True,
            show_progress=True,
            quiet=False,
        )

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_respects_quiet_mode(self, capsys: pytest.CaptureFixture) -> None:
        """Should respect quiet mode and not show message."""
        _show_interactive_sync_message(
            interactive_mode=True,
            show_progress=False,
            quiet=True,
        )

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_no_message_in_non_interactive_mode(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should not show message in non-interactive mode."""
        _show_interactive_sync_message(
            interactive_mode=False,
            show_progress=False,
            quiet=False,
        )

        captured = capsys.readouterr()
        assert captured.err == ""


class TestSyncCompletionMessage:
    """Tests for sync completion message destination."""

    def test_completion_message_goes_to_stderr(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Sync completion messages should go to stderr (status output)."""
        _show_sync_completion_message(success=True, files_indexed=5)

        captured = capsys.readouterr()
        assert "Synced 5 file(s)" in captured.err
        assert captured.out == ""

    def test_up_to_date_message_goes_to_stderr(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Index up to date message should go to stderr."""
        _show_sync_completion_message(success=True, files_indexed=0)

        captured = capsys.readouterr()
        assert "up to date" in captured.err
        assert captured.out == ""

    def test_no_message_on_failure(self, capsys: pytest.CaptureFixture) -> None:
        """Should not show completion message on failure."""
        _show_sync_completion_message(success=False, files_indexed=5)

        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""
