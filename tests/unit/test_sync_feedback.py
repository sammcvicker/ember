"""Tests for sync feedback message formatting.

Verifies that the CLI provides clear, accurate feedback about sync operations,
distinguishing between incremental and full scans.
"""

from dataclasses import dataclass
from unittest.mock import patch


@dataclass
class MockIndexResponse:
    """Mock IndexResponse for testing sync feedback."""

    files_indexed: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0
    chunks_deleted: int = 0
    vectors_stored: int = 0
    tree_sha: str = "abc123def456"
    files_failed: int = 0
    is_incremental: bool = False
    success: bool = True
    error: str | None = None


class TestFormatSyncResults:
    """Tests for _format_sync_results function."""

    def test_no_changes_full_scan(self) -> None:
        """Full scan with no changes shows 'full scan completed'."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=0,
            chunks_deleted=0,
            is_incremental=False,
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            mock_echo.assert_called_once_with("✓ No changes detected (full scan completed)")

    def test_no_changes_incremental_scan(self) -> None:
        """Incremental scan with no changes shows 'incremental scan completed'."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=0,
            chunks_deleted=0,
            is_incremental=True,
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            mock_echo.assert_called_once_with("✓ No changes detected (incremental scan completed)")

    def test_changes_detected_full_sync(self) -> None:
        """Full sync with changes shows correct sync type."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=5,
            chunks_created=10,
            chunks_deleted=0,
            is_incremental=False,
            tree_sha="abc123def456",
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            assert "✓ Indexed 5 files (full sync)" in calls

    def test_changes_detected_incremental_sync(self) -> None:
        """Incremental sync with changes shows correct sync type."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=3,
            chunks_created=6,
            chunks_deleted=0,
            is_incremental=True,
            tree_sha="abc123def456",
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            assert "✓ Indexed 3 files (incremental sync)" in calls

    def test_chunks_deleted_shows_details(self) -> None:
        """Deleted chunks are shown in output."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=0,
            chunks_deleted=5,
            is_incremental=True,
            tree_sha="abc123def456",
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            # When only chunks are deleted (no files indexed), it still counts as changes
            assert any("5 chunks deleted" in call for call in calls)

    def test_tree_sha_shown_when_changes(self) -> None:
        """Tree SHA is shown when there are changes."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=2,
            chunks_created=4,
            chunks_deleted=0,
            is_incremental=False,
            tree_sha="abc123def456789",
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            assert any("Tree SHA: abc123def456..." in call for call in calls)

    def test_tree_sha_not_shown_when_no_changes(self) -> None:
        """Tree SHA is not shown when there are no changes."""
        from ember.entrypoints.cli import _format_sync_results

        response = MockIndexResponse(
            files_indexed=0,
            chunks_deleted=0,
            is_incremental=False,
            tree_sha="abc123def456789",
        )

        with patch("click.echo") as mock_echo:
            _format_sync_results(response)
            calls = [call.args[0] for call in mock_echo.call_args_list]
            assert not any("Tree SHA" in call for call in calls)
