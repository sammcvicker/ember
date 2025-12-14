"""File preprocessing service for indexing pipeline.

Handles file I/O, content decoding, hashing, and language detection
as a single responsibility, separate from indexing orchestration.
"""

from dataclasses import dataclass
from pathlib import Path

import blake3

from ember.ports.fs import FileSystem

# Language extension mapping
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "py",
    ".pyi": "py",
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "js",
    ".jsx": "js",
    ".mjs": "js",
    ".cjs": "js",
    ".go": "go",
    ".rs": "rs",
    ".java": "java",
    ".kt": "java",
    ".scala": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cs": "cs",
    ".rb": "rb",
    ".php": "php",
    ".swift": "swift",
    ".sh": "sh",
    ".bash": "sh",
    ".zsh": "sh",
    ".vue": "vue",
    ".svelte": "svelte",
    ".sql": "sql",
    ".proto": "proto",
    ".graphql": "graphql",
    ".md": "txt",
    ".txt": "txt",
}


@dataclass(frozen=True)
class PreprocessedFile:
    """Result of preprocessing a file for indexing.

    Attributes:
        rel_path: Relative path from repository root.
        content: Decoded text content of the file.
        file_hash: BLAKE3 hash of the file content.
        file_size: Size of the file in bytes.
        lang: Detected language code (py, ts, go, etc.).
    """

    rel_path: Path
    content: str
    file_hash: str
    file_size: int
    lang: str


class FilePreprocessor:
    """Service for preprocessing files before indexing.

    Handles:
    - Reading file content from filesystem
    - Computing content hash (BLAKE3)
    - Decoding bytes to UTF-8 string
    - Detecting language from file extension

    This service is designed to be independently testable and
    separates file I/O concerns from indexing orchestration.
    """

    def __init__(self, fs: FileSystem) -> None:
        """Initialize the file preprocessor.

        Args:
            fs: File system adapter for reading files.
        """
        self.fs = fs

    def preprocess(self, file_path: Path, repo_root: Path) -> PreprocessedFile:
        """Preprocess a file for indexing.

        Reads the file, computes its hash, decodes content to string,
        and detects the programming language.

        Args:
            file_path: Absolute path to the file.
            repo_root: Repository root for computing relative path.

        Returns:
            PreprocessedFile with all computed attributes.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            PermissionError: If the file can't be read.
            OSError: For other I/O errors.
        """
        # Compute relative path
        rel_path = file_path.relative_to(repo_root)

        # Read file content (returns bytes)
        content_bytes = self.fs.read(file_path)

        # Compute hash and size from original bytes
        file_hash = blake3.blake3(content_bytes).hexdigest()
        file_size = len(content_bytes)

        # Decode to string for chunking
        content = self._decode_content(content_bytes)

        # Detect language from file extension
        lang = self._detect_language(file_path)

        return PreprocessedFile(
            rel_path=rel_path,
            content=content,
            file_hash=file_hash,
            file_size=file_size,
            lang=lang,
        )

    def _decode_content(self, content_bytes: bytes) -> str:
        """Decode bytes to UTF-8 string with fallback.

        Args:
            content_bytes: Raw file content as bytes.

        Returns:
            Decoded string content.
        """
        try:
            return content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Fall back to replace mode if strict UTF-8 fails
            return content_bytes.decode("utf-8", errors="replace")

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension.

        Args:
            file_path: Path to the file.

        Returns:
            Language code (py, ts, go, rs, txt, etc.).
        """
        suffix = file_path.suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(suffix, "txt")
