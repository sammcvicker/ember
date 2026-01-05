"""Unit tests for FilePreprocessor service.

Tests file I/O, hashing, content decoding, and language detection.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from ember.core.indexing.file_preprocessor import (
    FilePreprocessor,
    PreprocessedFile,
)
from ember.core.languages import LANGUAGE_REGISTRY


@pytest.fixture
def mock_fs() -> Mock:
    """Create a mock FileSystem."""
    return Mock()


@pytest.fixture
def preprocessor(mock_fs: Mock) -> FilePreprocessor:
    """Create FilePreprocessor with mock filesystem."""
    return FilePreprocessor(mock_fs)


class TestPreprocessedFile:
    """Tests for PreprocessedFile dataclass."""

    def test_preprocessed_file_is_frozen(self) -> None:
        """PreprocessedFile should be immutable."""
        pf = PreprocessedFile(
            rel_path=Path("test.py"),
            content="def hello(): pass",
            file_hash="abc123",
            file_size=17,
            lang="py",
        )
        with pytest.raises(AttributeError):
            pf.content = "modified"  # type: ignore[misc]

    def test_preprocessed_file_stores_all_fields(self) -> None:
        """PreprocessedFile should store all provided fields."""
        pf = PreprocessedFile(
            rel_path=Path("src/utils.py"),
            content="# utils",
            file_hash="def456",
            file_size=7,
            lang="py",
        )
        assert pf.rel_path == Path("src/utils.py")
        assert pf.content == "# utils"
        assert pf.file_hash == "def456"
        assert pf.file_size == 7
        assert pf.lang == "py"


class TestFilePreprocessorPreprocess:
    """Tests for FilePreprocessor.preprocess() method."""

    def test_preprocess_computes_relative_path(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should compute correct relative path."""
        mock_fs.read.return_value = b"content"

        result = preprocessor.preprocess(
            file_path=Path("/repo/src/app.py"),
            repo_root=Path("/repo"),
        )

        assert result.rel_path == Path("src/app.py")

    def test_preprocess_computes_file_hash(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should compute BLAKE3 hash of content."""
        import blake3

        content = b"def hello(): pass"
        mock_fs.read.return_value = content
        expected_hash = blake3.blake3(content).hexdigest()

        result = preprocessor.preprocess(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
        )

        assert result.file_hash == expected_hash

    def test_preprocess_computes_file_size(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should compute correct file size in bytes."""
        content = b"12345"
        mock_fs.read.return_value = content

        result = preprocessor.preprocess(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
        )

        assert result.file_size == 5

    def test_preprocess_decodes_utf8_content(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should decode UTF-8 content correctly."""
        content = "def hello(): pass"
        mock_fs.read.return_value = content.encode("utf-8")

        result = preprocessor.preprocess(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
        )

        assert result.content == content

    def test_preprocess_handles_invalid_utf8(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should handle invalid UTF-8 with replacement."""
        # Invalid UTF-8 sequence
        mock_fs.read.return_value = b"def test(): x = \xff\xff"

        result = preprocessor.preprocess(
            file_path=Path("/repo/test.py"),
            repo_root=Path("/repo"),
        )

        # Should contain replacement characters
        assert "def test():" in result.content
        assert "\ufffd" in result.content  # Unicode replacement character

    def test_preprocess_detects_python_language(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should detect Python language from extension."""
        mock_fs.read.return_value = b"content"

        result = preprocessor.preprocess(
            file_path=Path("/repo/app.py"),
            repo_root=Path("/repo"),
        )

        assert result.lang == "py"

    def test_preprocess_detects_typescript_language(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should detect TypeScript language from extension."""
        mock_fs.read.return_value = b"content"

        result = preprocessor.preprocess(
            file_path=Path("/repo/app.tsx"),
            repo_root=Path("/repo"),
        )

        assert result.lang == "ts"

    def test_preprocess_returns_txt_for_unknown_extension(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should return 'txt' for unknown extensions."""
        mock_fs.read.return_value = b"content"

        result = preprocessor.preprocess(
            file_path=Path("/repo/config.yaml"),
            repo_root=Path("/repo"),
        )

        assert result.lang == "txt"


class TestFilePreprocessorLanguageDetection:
    """Tests for language detection from file extensions."""

    def test_extension_mapping_covers_common_languages(self) -> None:
        """LANGUAGE_REGISTRY should cover all common code extensions."""
        expected_extensions = {
            ".py", ".pyi",  # Python
            ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",  # JavaScript/TypeScript
            ".go",  # Go
            ".rs",  # Rust
            ".java", ".kt", ".scala",  # JVM
            ".c", ".h", ".cpp", ".cc", ".hpp",  # C/C++
            ".cs",  # C#
            ".rb",  # Ruby
            ".php",  # PHP
            ".swift",  # Swift
            ".sh", ".bash", ".zsh",  # Shell
        }
        for ext in expected_extensions:
            assert ext in LANGUAGE_REGISTRY, f"Missing extension: {ext}"

    def test_detect_language_is_case_insensitive(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """Language detection should be case-insensitive."""
        mock_fs.read.return_value = b"content"

        result = preprocessor.preprocess(
            file_path=Path("/repo/App.PY"),  # Uppercase extension
            repo_root=Path("/repo"),
        )

        assert result.lang == "py"


class TestFilePreprocessorErrorHandling:
    """Tests for error handling in FilePreprocessor."""

    def test_preprocess_propagates_file_not_found(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should propagate FileNotFoundError."""
        mock_fs.read.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            preprocessor.preprocess(
                file_path=Path("/repo/missing.py"),
                repo_root=Path("/repo"),
            )

    def test_preprocess_propagates_permission_error(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should propagate PermissionError."""
        mock_fs.read.side_effect = PermissionError("Access denied")

        with pytest.raises(PermissionError):
            preprocessor.preprocess(
                file_path=Path("/repo/secret.py"),
                repo_root=Path("/repo"),
            )

    def test_preprocess_propagates_os_error(
        self, preprocessor: FilePreprocessor, mock_fs: Mock
    ) -> None:
        """preprocess() should propagate OSError."""
        mock_fs.read.side_effect = OSError("Disk error")

        with pytest.raises(OSError):
            preprocessor.preprocess(
                file_path=Path("/repo/test.py"),
                repo_root=Path("/repo"),
            )
