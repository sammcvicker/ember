"""Unified language registry for all Ember components.

Single source of truth for language/extension mappings used by:
- File preprocessing (semantic language codes)
- Syntax highlighting (Pygments lexer names)
- File filtering (code file detection)

To add a new language, add a single entry to LANGUAGE_REGISTRY.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class LanguageInfo:
    """Information about a programming language.

    Attributes:
        semantic: Language code for semantic processing (e.g., "py", "ts").
            Used by tree-sitter and chunking.
        lexer: Pygments lexer name for syntax highlighting (e.g., "python").
        is_code: Whether this extension represents indexable source code.
    """

    semantic: str
    lexer: str
    is_code: bool = True


# Master registry mapping file extensions to language info.
# This is the SINGLE SOURCE OF TRUTH for all language mappings.
LANGUAGE_REGISTRY: Final[dict[str, LanguageInfo]] = {
    # Python
    ".py": LanguageInfo(semantic="py", lexer="python"),
    ".pyi": LanguageInfo(semantic="py", lexer="python"),
    # JavaScript/TypeScript
    ".js": LanguageInfo(semantic="js", lexer="javascript"),
    ".jsx": LanguageInfo(semantic="js", lexer="javascript"),
    ".mjs": LanguageInfo(semantic="js", lexer="javascript"),
    ".cjs": LanguageInfo(semantic="js", lexer="javascript"),
    ".ts": LanguageInfo(semantic="ts", lexer="typescript"),
    ".tsx": LanguageInfo(semantic="ts", lexer="typescript"),
    # Go
    ".go": LanguageInfo(semantic="go", lexer="go"),
    # Rust
    ".rs": LanguageInfo(semantic="rs", lexer="rust"),
    # Java/JVM
    ".java": LanguageInfo(semantic="java", lexer="java"),
    ".kt": LanguageInfo(semantic="java", lexer="kotlin"),
    ".scala": LanguageInfo(semantic="java", lexer="scala"),
    # C/C++
    ".c": LanguageInfo(semantic="c", lexer="c"),
    ".h": LanguageInfo(semantic="c", lexer="c"),
    ".cpp": LanguageInfo(semantic="cpp", lexer="cpp"),
    ".cc": LanguageInfo(semantic="cpp", lexer="cpp"),
    ".cxx": LanguageInfo(semantic="cpp", lexer="cpp"),
    ".hpp": LanguageInfo(semantic="cpp", lexer="cpp"),
    ".hh": LanguageInfo(semantic="cpp", lexer="cpp"),
    ".hxx": LanguageInfo(semantic="cpp", lexer="cpp"),
    # C#
    ".cs": LanguageInfo(semantic="cs", lexer="csharp"),
    # Ruby
    ".rb": LanguageInfo(semantic="rb", lexer="ruby"),
    # PHP
    ".php": LanguageInfo(semantic="php", lexer="php"),
    # Swift
    ".swift": LanguageInfo(semantic="swift", lexer="swift"),
    # Shell
    ".sh": LanguageInfo(semantic="sh", lexer="bash"),
    ".bash": LanguageInfo(semantic="sh", lexer="bash"),
    ".zsh": LanguageInfo(semantic="sh", lexer="bash"),
    # Web frameworks
    ".vue": LanguageInfo(semantic="vue", lexer="vue"),
    ".svelte": LanguageInfo(semantic="svelte", lexer="html"),
    # Query/Schema languages
    ".sql": LanguageInfo(semantic="sql", lexer="sql"),
    ".proto": LanguageInfo(semantic="proto", lexer="protobuf"),
    ".graphql": LanguageInfo(semantic="graphql", lexer="graphql"),
    # Data/Config (highlighted but not indexed as code)
    ".yaml": LanguageInfo(semantic="txt", lexer="yaml", is_code=False),
    ".yml": LanguageInfo(semantic="txt", lexer="yaml", is_code=False),
    ".json": LanguageInfo(semantic="txt", lexer="json", is_code=False),
    ".toml": LanguageInfo(semantic="txt", lexer="toml", is_code=False),
    # Documentation (highlighted but not indexed as code)
    ".md": LanguageInfo(semantic="txt", lexer="markdown", is_code=False),
    ".txt": LanguageInfo(semantic="txt", lexer="text", is_code=False),
}

# Default for unknown extensions
_DEFAULT_LANGUAGE = LanguageInfo(semantic="txt", lexer="text", is_code=False)


def get_semantic_language(suffix: str) -> str:
    """Get the semantic language code for a file extension.

    Used by file preprocessing and chunking to identify language
    for tree-sitter parsing.

    Args:
        suffix: File extension with leading dot (e.g., ".py").

    Returns:
        Language code (e.g., "py", "ts", "go"). Defaults to "txt".
    """
    suffix = suffix.lower()
    return LANGUAGE_REGISTRY.get(suffix, _DEFAULT_LANGUAGE).semantic


def get_lexer_name(suffix: str) -> str:
    """Get the Pygments lexer name for a file extension.

    Used by syntax highlighting to determine the appropriate lexer.

    Args:
        suffix: File extension with leading dot (e.g., ".py").

    Returns:
        Pygments lexer name (e.g., "python", "typescript"). Defaults to "text".
    """
    suffix = suffix.lower()
    return LANGUAGE_REGISTRY.get(suffix, _DEFAULT_LANGUAGE).lexer


def is_code_file(suffix: str) -> bool:
    """Check if a file extension represents indexable source code.

    Used by file filtering to determine which files to index.
    Config, data, and documentation files return False.

    Args:
        suffix: File extension with leading dot (e.g., ".py").

    Returns:
        True if the extension represents indexable source code.
    """
    suffix = suffix.lower()
    info = LANGUAGE_REGISTRY.get(suffix)
    return info.is_code if info else False


def get_code_file_extensions() -> frozenset[str]:
    """Get all file extensions that represent indexable source code.

    Returns:
        Frozenset of extensions (e.g., {".py", ".ts", ".go", ...}).
    """
    return frozenset(ext for ext, info in LANGUAGE_REGISTRY.items() if info.is_code)
