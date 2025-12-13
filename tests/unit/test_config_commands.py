"""Unit tests for ember config CLI commands."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ember.entrypoints.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestConfigShow:
    """Tests for 'ember config show' command."""

    def test_show_global_only(self, runner: CliRunner) -> None:
        """Test showing only global config location."""
        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=Path("/home/user/.config/ember/config.toml"),
        ):
            result = runner.invoke(cli, ["config", "show", "--global"], obj={})

        assert result.exit_code == 0
        assert "/home/user/.config/ember/config.toml" in result.output
        assert "Global config:" in result.output

    def test_show_local_not_in_repo(self, runner: CliRunner) -> None:
        """Test showing local config when not in a repository."""
        with patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            side_effect=RuntimeError("Not in repo"),
        ):
            result = runner.invoke(cli, ["config", "show", "--local"], obj={})

        assert result.exit_code == 0
        assert "Not in an Ember repository" in result.output

    def test_show_both_default(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test showing both configs by default."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        global_config = tmp_path / "global_config.toml"

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ):
            result = runner.invoke(cli, ["config", "show"], obj={})

        assert result.exit_code == 0
        assert "Global config:" in result.output
        assert "Local config:" in result.output

    def test_show_global_exists_status(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that global config shows 'exists' status when file exists."""
        global_config = tmp_path / "config.toml"
        global_config.write_text("[index]\nmodel = 'test'\n")

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            side_effect=RuntimeError("Not in repo"),
        ):
            result = runner.invoke(cli, ["config", "show", "--global"], obj={})

        assert result.exit_code == 0
        assert "exists" in result.output

    def test_show_global_not_created_status(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that global config shows 'not created' status when file doesn't exist."""
        global_config = tmp_path / "nonexistent.toml"

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            side_effect=RuntimeError("Not in repo"),
        ):
            result = runner.invoke(cli, ["config", "show", "--global"], obj={})

        assert result.exit_code == 0
        assert "not created" in result.output

    def test_show_local_exists_status(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that local config shows 'exists' status when file exists."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        local_config = ember_dir / "config.toml"
        local_config.write_text("[index]\nmodel = 'test'\n")
        global_config = tmp_path / "global.toml"

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ):
            result = runner.invoke(cli, ["config", "show", "--local"], obj={})

        assert result.exit_code == 0
        assert "exists" in result.output

    def test_show_local_not_created_status(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that local config shows 'not created' status when file doesn't exist."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        global_config = tmp_path / "global.toml"

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ):
            result = runner.invoke(cli, ["config", "show", "--local"], obj={})

        assert result.exit_code == 0
        assert "not created" in result.output

    def test_show_effective_config_in_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that effective merged config is shown when in a repo."""
        from ember.domain.config import EmberConfig

        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        global_config = tmp_path / "global.toml"

        mock_config = EmberConfig.default()

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ), patch(
            "ember.adapters.config.toml_config_provider.TomlConfigProvider.load",
            return_value=mock_config,
        ):
            result = runner.invoke(cli, ["config", "show"], obj={})

        assert result.exit_code == 0
        assert "Effective configuration" in result.output
        assert "[index]" in result.output
        assert "[model]" in result.output
        assert "[search]" in result.output
        assert "[display]" in result.output

    def test_show_global_config_content(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that global config content is shown when --global and file exists."""
        from ember.domain.config import EmberConfig

        global_config = tmp_path / "config.toml"
        global_config.write_text("[index]\nmodel = 'test'\n")

        mock_config = EmberConfig.default()

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            side_effect=RuntimeError("Not in repo"),
        ), patch(
            "ember.shared.config_io.load_config",
            return_value=mock_config,
        ):
            result = runner.invoke(cli, ["config", "show", "--global"], obj={})

        assert result.exit_code == 0
        assert "Global configuration:" in result.output

    def test_show_config_load_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that config load errors are displayed gracefully."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()
        global_config = tmp_path / "global.toml"

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=global_config,
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ), patch(
            "ember.adapters.config.toml_config_provider.TomlConfigProvider.load",
            side_effect=ValueError("Invalid config format"),
        ):
            result = runner.invoke(cli, ["config", "show"], obj={})

        assert result.exit_code == 0
        assert "Error loading config" in result.output


class TestConfigPath:
    """Tests for 'ember config path' command."""

    def test_path_global_only(self, runner: CliRunner) -> None:
        """Test getting global config path only."""
        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=Path("/home/user/.config/ember/config.toml"),
        ):
            result = runner.invoke(cli, ["config", "path", "--global"], obj={})

        assert result.exit_code == 0
        assert result.output.strip() == "/home/user/.config/ember/config.toml"

    def test_path_local_only_in_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test getting local config path when in a repository."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        with patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ):
            result = runner.invoke(cli, ["config", "path", "--local"], obj={})

        assert result.exit_code == 0
        assert str(ember_dir / "config.toml") in result.output

    def test_path_both(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test getting both config paths."""
        ember_dir = tmp_path / ".ember"
        ember_dir.mkdir()

        with patch(
            "ember.shared.config_io.get_global_config_path",
            return_value=Path("/home/user/.config/ember/config.toml"),
        ), patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            return_value=(tmp_path, ember_dir),
        ):
            result = runner.invoke(cli, ["config", "path"], obj={})

        assert result.exit_code == 0
        assert "global:" in result.output
        assert "local:" in result.output


class TestConfigEdit:
    """Tests for 'ember config edit' command."""

    def test_edit_global_not_in_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test editing global config when not in a repository."""
        global_config = tmp_path / "config.toml"

        with (
            patch(
                "ember.shared.config_io.get_global_config_path",
                return_value=global_config,
            ),
            patch(
                "ember.entrypoints.cli.get_ember_repo_root",
                side_effect=RuntimeError("Not in repo"),
            ),
            patch.dict("os.environ", {"EDITOR": "echo"}),
        ):
            result = runner.invoke(cli, ["config", "edit", "--global"], obj={})

        assert result.exit_code == 0
        # Config file should be created
        assert global_config.exists()

    def test_edit_local_not_in_repo_fails(self, runner: CliRunner) -> None:
        """Test that editing local config fails when not in a repository."""
        with patch(
            "ember.entrypoints.cli.get_ember_repo_root",
            side_effect=RuntimeError("Not in repo"),
        ):
            result = runner.invoke(cli, ["config", "edit"], obj={})

        assert result.exit_code == 1
        assert "Not in an Ember repository" in result.output
