"""Unit tests for init command helper functions.

Tests for _select_embedding_model, _display_system_resources,
_prompt_for_model_choice, and _report_init_results.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from ember.core.hardware import GPUResources, SystemResources


class TestSelectEmbeddingModel:
    """Tests for _select_embedding_model function."""

    def test_returns_explicit_model_when_provided(self) -> None:
        """Should return user-specified model without prompting."""
        from ember.entrypoints.cli import _select_embedding_model

        result = _select_embedding_model(
            model="minilm",
            quiet=False,
            yes=False,
        )

        assert result == "minilm"

    def test_returns_recommended_model_with_yes_flag(self) -> None:
        """Should return recommended model when --yes is set."""
        from ember.entrypoints.cli import _select_embedding_model

        with patch("ember.entrypoints.cli.click.echo"), patch(
            "ember.core.hardware.detect_system_resources"
        ) as mock_detect:
            mock_detect.return_value = SystemResources(
                available_ram_gb=2.0,
                total_ram_gb=8.0,
                gpu=None,
            )

            result = _select_embedding_model(
                model=None,
                quiet=True,
                yes=True,
            )

            # 2GB RAM should recommend bge-small
            assert result == "bge-small"

    def test_returns_jina_when_resources_sufficient_and_quiet(self) -> None:
        """Should return jina-code-v2 for high-resource systems."""
        from ember.entrypoints.cli import _select_embedding_model

        with patch(
            "ember.core.hardware.detect_system_resources"
        ) as mock_detect:
            mock_detect.return_value = SystemResources(
                available_ram_gb=8.0,
                total_ram_gb=16.0,
                gpu=None,
            )

            result = _select_embedding_model(
                model=None,
                quiet=True,
                yes=False,
            )

            assert result == "jina-code-v2"

    def test_prompts_user_when_resources_limited(self) -> None:
        """Should prompt user when resources don't support jina."""
        from ember.entrypoints.cli import _select_embedding_model

        with (
            patch("ember.entrypoints.cli.click.echo"),
            patch("ember.entrypoints.cli.click.confirm") as mock_confirm,
            patch("ember.core.hardware.detect_system_resources") as mock_detect,
        ):
            mock_confirm.return_value = True
            mock_detect.return_value = SystemResources(
                available_ram_gb=2.0,
                total_ram_gb=8.0,
                gpu=None,
            )

            result = _select_embedding_model(
                model=None,
                quiet=True,  # quiet to skip display
                yes=False,
            )

            # User accepted recommended model
            assert result == "bge-small"
            mock_confirm.assert_called_once()


class TestDisplaySystemResources:
    """Tests for _display_system_resources function."""

    def test_displays_ram_info(self) -> None:
        """Should display available RAM."""
        from ember.entrypoints.cli import _display_system_resources

        resources = SystemResources(
            available_ram_gb=4.5,
            total_ram_gb=16.0,
            gpu=None,
        )

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _display_system_resources(resources, "jina-code-v2", "reason text")

            # Verify RAM was displayed
            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("4.5GB" in call for call in calls)
            assert any("jina-code-v2" in call for call in calls)
            assert any("reason text" in call for call in calls)

    def test_displays_gpu_info_when_present(self) -> None:
        """Should display GPU info when available."""
        from ember.entrypoints.cli import _display_system_resources

        resources = SystemResources(
            available_ram_gb=8.0,
            total_ram_gb=16.0,
            gpu=GPUResources(
                device_name="NVIDIA RTX 4090",
                total_vram_gb=24.0,
                free_vram_gb=20.5,
                backend="cuda",
            ),
        )

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _display_system_resources(resources, "jina-code-v2", "reason")

            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("NVIDIA RTX 4090" in call for call in calls)
            assert any("24.0GB" in call for call in calls)
            assert any("20.5GB" in call for call in calls)


class TestPromptForModelChoice:
    """Tests for _prompt_for_model_choice function."""

    def test_returns_recommended_when_user_accepts(self) -> None:
        """Should return recommended model when user confirms."""
        from ember.entrypoints.cli import _prompt_for_model_choice

        resources = SystemResources(
            available_ram_gb=2.0,
            total_ram_gb=8.0,
            gpu=None,
        )

        with (
            patch("ember.entrypoints.cli.click.echo"),
            patch("ember.entrypoints.cli.click.confirm") as mock_confirm,
        ):
            mock_confirm.return_value = True
            result = _prompt_for_model_choice(resources, "bge-small")
            assert result == "bge-small"

    def test_returns_jina_when_user_declines(self) -> None:
        """Should return jina-code-v2 when user declines recommendation."""
        from ember.entrypoints.cli import _prompt_for_model_choice

        resources = SystemResources(
            available_ram_gb=2.0,
            total_ram_gb=8.0,
            gpu=None,
        )

        with (
            patch("ember.entrypoints.cli.click.echo"),
            patch("ember.entrypoints.cli.click.confirm") as mock_confirm,
        ):
            mock_confirm.return_value = False
            result = _prompt_for_model_choice(resources, "bge-small")
            assert result == "jina-code-v2"

    def test_shows_vram_warning_when_gpu_limited(self) -> None:
        """Should show VRAM warning when GPU memory is the limiting factor."""
        from ember.entrypoints.cli import _prompt_for_model_choice

        resources = SystemResources(
            available_ram_gb=16.0,  # Plenty of RAM
            total_ram_gb=32.0,
            gpu=GPUResources(
                device_name="Low VRAM GPU",
                total_vram_gb=4.0,
                free_vram_gb=1.5,  # But low VRAM
                backend="cuda",
            ),
        )

        with (
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
            patch("ember.entrypoints.cli.click.confirm"),
        ):
            _prompt_for_model_choice(resources, "bge-small")
            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("VRAM" in call for call in calls)

    def test_shows_ram_warning_when_ram_limited(self) -> None:
        """Should show RAM warning when system memory is the limiting factor."""
        from ember.entrypoints.cli import _prompt_for_model_choice

        resources = SystemResources(
            available_ram_gb=2.0,  # Low RAM
            total_ram_gb=8.0,
            gpu=None,
        )

        with (
            patch("ember.entrypoints.cli.click.echo") as mock_echo,
            patch("ember.entrypoints.cli.click.confirm"),
        ):
            _prompt_for_model_choice(resources, "bge-small")
            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("RAM" in call for call in calls)


class TestReportInitResults:
    """Tests for _report_init_results function."""

    def test_reports_new_init(self) -> None:
        """Should report successful new initialization."""
        from ember.entrypoints.cli import _report_init_results

        response = MagicMock()
        response.global_config_created = False
        response.was_reinitialized = False
        response.ember_dir = Path("/tmp/repo/.ember")
        response.config_path = MagicMock(name="config.toml")
        response.db_path = MagicMock(name="index.db")
        response.state_path = MagicMock(name="state.json")

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _report_init_results(response, "jina-code-v2", quiet=False)

            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("Initialized" in call for call in calls)
            assert any(".ember" in call for call in calls)

    def test_reports_reinit(self) -> None:
        """Should report reinitialization."""
        from ember.entrypoints.cli import _report_init_results

        response = MagicMock()
        response.global_config_created = False
        response.was_reinitialized = True
        response.ember_dir = Path("/tmp/repo/.ember")
        response.config_path = MagicMock(name="config.toml")
        response.db_path = MagicMock(name="index.db")
        response.state_path = MagicMock(name="state.json")

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _report_init_results(response, "jina-code-v2", quiet=False)

            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("Reinitialized" in call for call in calls)

    def test_reports_global_config_creation(self) -> None:
        """Should report global config creation on first run."""
        from ember.entrypoints.cli import _report_init_results

        response = MagicMock()
        response.global_config_created = True
        response.global_config_path = Path("/home/user/.config/ember/config.toml")
        response.was_reinitialized = False
        response.ember_dir = Path("/tmp/repo/.ember")
        response.config_path = MagicMock(name="config.toml")
        response.db_path = MagicMock(name="index.db")
        response.state_path = MagicMock(name="state.json")

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _report_init_results(response, "jina-code-v2", quiet=False)

            calls = [str(call) for call in mock_echo.call_args_list]
            assert any("global config" in call.lower() for call in calls)
            assert any("jina-code-v2" in call for call in calls)

    def test_quiet_mode_suppresses_details(self) -> None:
        """Should suppress detailed output in quiet mode."""
        from ember.entrypoints.cli import _report_init_results

        response = MagicMock()
        response.global_config_created = False
        response.was_reinitialized = False
        response.ember_dir = Path("/tmp/repo/.ember")

        with patch("ember.entrypoints.cli.click.echo") as mock_echo:
            _report_init_results(response, "jina-code-v2", quiet=True)

            # Only the basic success message should be shown
            calls = [str(call) for call in mock_echo.call_args_list]
            assert len(calls) == 1  # Only one message in quiet mode
            assert any("Initialized" in call for call in calls)
