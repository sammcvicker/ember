"""Unit tests for model download error handling in CLI.

Tests for improved error messages when model download fails during init.
Issue #393: CLI model download errors are too generic and unhelpful.
"""

from unittest.mock import MagicMock, patch

import pytest

from ember.entrypoints.cli import _ensure_model_downloaded


class TestEnsureModelDownloadedErrors:
    """Tests for _ensure_model_downloaded error handling."""

    def test_returns_true_when_model_cached(self) -> None:
        """Should return True immediately when model is already cached."""
        with patch(
            "ember.adapters.local_models.is_model_cached", return_value=True
        ) as mock_cached:
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is True
            mock_cached.assert_called_once_with("jina-code-v2")

    def test_returns_true_on_successful_download(self) -> None:
        """Should return True when model downloads successfully."""
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

    def test_network_error_shows_specific_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show network-specific error message for connection failures."""
        import requests

        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should identify it as a network error
            assert (
                "network" in captured.out.lower()
                or "connection" in captured.out.lower()
            )
            # Should suggest a smaller model as fallback
            assert "bge-small" in captured.out.lower()

    def test_disk_space_error_shows_specific_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show disk space error message for 'No space left' errors."""
        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = OSError("No space left on device")

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should identify disk space issue
            assert "space" in captured.out.lower() or "disk" in captured.out.lower()
            # Should suggest freeing up space
            assert "free" in captured.out.lower() or "GB" in captured.out

    def test_permission_error_shows_specific_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show permission error message for 'Permission denied' errors."""
        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = OSError(
            "Permission denied: ~/.cache/huggingface"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should identify permission issue
            assert "permission" in captured.out.lower()
            # Should mention the cache directory
            assert (
                "huggingface" in captured.out.lower() or "cache" in captured.out.lower()
            )

    def test_generic_oserror_shows_filesystem_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show generic filesystem error for other OSError cases."""
        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = OSError("Some other filesystem error")

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should show the error message
            assert (
                "file system" in captured.out.lower()
                or "filesystem" in captured.out.lower()
            )

    def test_timeout_error_shows_specific_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show timeout-specific error message."""
        import requests

        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = requests.exceptions.Timeout(
            "Connection timed out"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should identify timeout
            assert (
                "timeout" in captured.out.lower() or "timed out" in captured.out.lower()
            )

    def test_generic_exception_shows_fallback_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should show generic message for unexpected exceptions."""
        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = RuntimeError(
            "Unexpected model loading error"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should show the error
            assert "failed" in captured.out.lower()
            # Should suggest verbose mode or help
            assert "verbose" in captured.out.lower() or "help" in captured.out.lower()

    def test_quiet_mode_still_shows_critical_errors(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should NOT silently fail in quiet mode - show critical error info."""
        import requests

        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=True)

            assert result is False
            captured = capsys.readouterr()
            # In quiet mode, should still show critical error
            # (the issue says "Never silently fail in quiet mode for critical operations")
            assert len(captured.out.strip()) > 0
            assert "error" in captured.out.lower() or "failed" in captured.out.lower()

    def test_quiet_mode_suppresses_progress_messages(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should suppress progress messages in quiet mode on success."""
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
            captured = capsys.readouterr()
            # Should not show download progress in quiet mode
            assert "downloading" not in captured.out.lower()

    def test_suggests_smaller_model_for_large_downloads(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should suggest smaller model when downloading large models fails."""
        import requests

        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = requests.exceptions.ConnectionError(
            "Connection failed"
        )

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            # Test with jina model (large)
            _ensure_model_downloaded("jina-code-v2", quiet=False)

            captured = capsys.readouterr()
            # Should suggest bge-small as alternative
            assert "bge-small" in captured.out.lower()

    def test_url_error_shows_network_message(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Should handle urllib errors as network errors."""
        from urllib.error import URLError

        mock_embedder = MagicMock()
        mock_embedder.ensure_loaded.side_effect = URLError("Name or service not known")

        with (
            patch("ember.adapters.local_models.is_model_cached", return_value=False),
            patch(
                "ember.adapters.local_models.create_embedder",
                return_value=mock_embedder,
            ),
        ):
            result = _ensure_model_downloaded("jina-code-v2", quiet=False)

            assert result is False
            captured = capsys.readouterr()
            # Should identify as network error
            assert (
                "network" in captured.out.lower()
                or "connection" in captured.out.lower()
            )
