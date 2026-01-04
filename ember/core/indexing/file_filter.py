"""File filtering service for selecting indexable code files.

Filters files based on:
- Code file extensions (whitelist approach)
- Glob pattern matching for path filters
"""

from pathlib import Path

# Code file extensions to index (whitelist approach)
# Only source code files are indexed - data, config, docs, and binary files are skipped
CODE_FILE_EXTENSIONS = frozenset(
    {
        # Python
        ".py",
        ".pyi",
        # JavaScript/TypeScript
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        # Go
        ".go",
        # Rust
        ".rs",
        # Java/JVM
        ".java",
        ".kt",
        ".scala",
        # C/C++
        ".c",
        ".cpp",
        ".cc",
        ".cxx",
        ".h",
        ".hpp",
        ".hh",
        ".hxx",
        # C#
        ".cs",
        # Ruby
        ".rb",
        # PHP
        ".php",
        # Swift
        ".swift",
        # Shell
        ".sh",
        ".bash",
        ".zsh",
        # Web frameworks
        ".vue",
        ".svelte",
        # Other
        ".sql",
        ".proto",
        ".graphql",
    }
)


class FileFilterService:
    """Filters files to identify indexable code files.

    Applies two types of filtering:
    1. Extension-based filtering to include only code files
    2. Glob pattern filtering to match user-specified paths
    """

    def is_code_file(self, file_path: Path) -> bool:
        """Check if file is a code file that should be indexed.

        Args:
            file_path: Path to file.

        Returns:
            True if file should be indexed, False otherwise.
        """
        suffix = file_path.suffix.lower()
        return suffix in CODE_FILE_EXTENSIONS

    def filter_code_files(self, files: list[Path]) -> list[Path]:
        """Filter list to only include code files.

        Args:
            files: List of file paths.

        Returns:
            Filtered list containing only code files.
        """
        return [f for f in files if self.is_code_file(f)]

    def apply_path_filters(
        self,
        files: list[Path],
        path_filters: list[str],
        repo_root: Path,
    ) -> list[Path]:
        """Apply glob pattern filters to file list.

        Args:
            files: List of absolute file paths.
            path_filters: Glob patterns to match against.
            repo_root: Repository root for computing relative paths.

        Returns:
            Filtered list of files matching at least one pattern.
        """
        filtered = []
        for f in files:
            try:
                rel_path = f.relative_to(repo_root)
            except ValueError:
                # File is not relative to repo_root, skip it
                continue

            for pattern in path_filters:
                if rel_path.match(pattern):
                    filtered.append(f)
                    break
        return filtered
