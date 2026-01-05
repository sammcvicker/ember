"""Tests for the unified language registry.

Verifies that the language registry provides consistent mappings
for semantic language codes, Pygments lexer names, and code file detection.
"""

import pytest

from ember.core.languages import (
    LANGUAGE_REGISTRY,
    LanguageInfo,
    get_code_file_extensions,
    get_lexer_name,
    get_semantic_language,
    is_code_file,
)


class TestLanguageInfo:
    """Tests for the LanguageInfo dataclass."""

    def test_language_info_is_frozen(self) -> None:
        """LanguageInfo should be immutable."""
        info = LanguageInfo(semantic="py", lexer="python")
        with pytest.raises(AttributeError):
            info.semantic = "changed"  # type: ignore[misc]

    def test_language_info_defaults(self) -> None:
        """LanguageInfo should default is_code to True."""
        info = LanguageInfo(semantic="py", lexer="python")
        assert info.is_code is True

    def test_language_info_explicit_is_code(self) -> None:
        """LanguageInfo should accept explicit is_code value."""
        info = LanguageInfo(semantic="txt", lexer="yaml", is_code=False)
        assert info.is_code is False


class TestLanguageRegistry:
    """Tests for the LANGUAGE_REGISTRY dictionary."""

    def test_registry_is_not_empty(self) -> None:
        """Registry should contain language entries."""
        assert len(LANGUAGE_REGISTRY) > 0

    def test_all_entries_have_valid_structure(self) -> None:
        """All registry entries should be valid LanguageInfo instances."""
        for ext, info in LANGUAGE_REGISTRY.items():
            assert isinstance(ext, str), f"Extension should be string: {ext}"
            assert ext.startswith("."), f"Extension should start with dot: {ext}"
            assert isinstance(info, LanguageInfo), f"Value should be LanguageInfo: {ext}"
            assert len(info.semantic) > 0, f"Semantic should not be empty: {ext}"
            assert len(info.lexer) > 0, f"Lexer should not be empty: {ext}"

    def test_python_extensions(self) -> None:
        """Python extensions should map correctly."""
        assert LANGUAGE_REGISTRY[".py"].semantic == "py"
        assert LANGUAGE_REGISTRY[".py"].lexer == "python"
        assert LANGUAGE_REGISTRY[".py"].is_code is True
        assert LANGUAGE_REGISTRY[".pyi"].semantic == "py"

    def test_javascript_extensions(self) -> None:
        """JavaScript/TypeScript extensions should map correctly."""
        # JavaScript
        assert LANGUAGE_REGISTRY[".js"].semantic == "js"
        assert LANGUAGE_REGISTRY[".js"].lexer == "javascript"
        assert LANGUAGE_REGISTRY[".jsx"].semantic == "js"
        assert LANGUAGE_REGISTRY[".mjs"].semantic == "js"
        assert LANGUAGE_REGISTRY[".cjs"].semantic == "js"
        # TypeScript
        assert LANGUAGE_REGISTRY[".ts"].semantic == "ts"
        assert LANGUAGE_REGISTRY[".ts"].lexer == "typescript"
        assert LANGUAGE_REGISTRY[".tsx"].semantic == "ts"

    def test_systems_languages(self) -> None:
        """Systems languages should map correctly."""
        # Go
        assert LANGUAGE_REGISTRY[".go"].semantic == "go"
        assert LANGUAGE_REGISTRY[".go"].lexer == "go"
        # Rust
        assert LANGUAGE_REGISTRY[".rs"].semantic == "rs"
        assert LANGUAGE_REGISTRY[".rs"].lexer == "rust"
        # C
        assert LANGUAGE_REGISTRY[".c"].semantic == "c"
        assert LANGUAGE_REGISTRY[".h"].semantic == "c"
        # C++
        assert LANGUAGE_REGISTRY[".cpp"].semantic == "cpp"
        assert LANGUAGE_REGISTRY[".hpp"].semantic == "cpp"

    def test_config_files_not_code(self) -> None:
        """Config/data files should not be marked as code."""
        assert LANGUAGE_REGISTRY[".yaml"].is_code is False
        assert LANGUAGE_REGISTRY[".yml"].is_code is False
        assert LANGUAGE_REGISTRY[".json"].is_code is False
        assert LANGUAGE_REGISTRY[".toml"].is_code is False
        assert LANGUAGE_REGISTRY[".md"].is_code is False

    def test_config_files_have_lexers(self) -> None:
        """Config/data files should still have lexers for highlighting."""
        assert LANGUAGE_REGISTRY[".yaml"].lexer == "yaml"
        assert LANGUAGE_REGISTRY[".json"].lexer == "json"
        assert LANGUAGE_REGISTRY[".toml"].lexer == "toml"
        assert LANGUAGE_REGISTRY[".md"].lexer == "markdown"


class TestGetSemanticLanguage:
    """Tests for get_semantic_language function."""

    def test_known_extension(self) -> None:
        """Known extensions should return correct semantic code."""
        assert get_semantic_language(".py") == "py"
        assert get_semantic_language(".ts") == "ts"
        assert get_semantic_language(".go") == "go"
        assert get_semantic_language(".rs") == "rs"

    def test_unknown_extension_returns_txt(self) -> None:
        """Unknown extensions should return 'txt'."""
        assert get_semantic_language(".xyz") == "txt"
        assert get_semantic_language(".unknown") == "txt"
        assert get_semantic_language("") == "txt"

    def test_case_insensitive(self) -> None:
        """Extension lookup should be case-insensitive."""
        assert get_semantic_language(".PY") == "py"
        assert get_semantic_language(".Ts") == "ts"
        assert get_semantic_language(".GO") == "go"


class TestGetLexerName:
    """Tests for get_lexer_name function."""

    def test_known_extension(self) -> None:
        """Known extensions should return correct lexer name."""
        assert get_lexer_name(".py") == "python"
        assert get_lexer_name(".ts") == "typescript"
        assert get_lexer_name(".go") == "go"
        assert get_lexer_name(".rs") == "rust"

    def test_unknown_extension_returns_text(self) -> None:
        """Unknown extensions should return 'text'."""
        assert get_lexer_name(".xyz") == "text"
        assert get_lexer_name(".unknown") == "text"
        assert get_lexer_name("") == "text"

    def test_case_insensitive(self) -> None:
        """Extension lookup should be case-insensitive."""
        assert get_lexer_name(".PY") == "python"
        assert get_lexer_name(".Ts") == "typescript"
        assert get_lexer_name(".GO") == "go"


class TestIsCodeFile:
    """Tests for is_code_file function."""

    def test_code_files_return_true(self) -> None:
        """Code file extensions should return True."""
        assert is_code_file(".py") is True
        assert is_code_file(".ts") is True
        assert is_code_file(".go") is True
        assert is_code_file(".rs") is True
        assert is_code_file(".java") is True

    def test_config_files_return_false(self) -> None:
        """Config/data file extensions should return False."""
        assert is_code_file(".yaml") is False
        assert is_code_file(".yml") is False
        assert is_code_file(".json") is False
        assert is_code_file(".toml") is False
        assert is_code_file(".md") is False

    def test_unknown_extension_returns_false(self) -> None:
        """Unknown extensions should return False."""
        assert is_code_file(".xyz") is False
        assert is_code_file(".unknown") is False
        assert is_code_file("") is False

    def test_case_insensitive(self) -> None:
        """Extension lookup should be case-insensitive."""
        assert is_code_file(".PY") is True
        assert is_code_file(".Ts") is True
        assert is_code_file(".YAML") is False


class TestGetCodeFileExtensions:
    """Tests for get_code_file_extensions function."""

    def test_returns_frozenset(self) -> None:
        """Should return an immutable frozenset."""
        result = get_code_file_extensions()
        assert isinstance(result, frozenset)

    def test_contains_code_extensions(self) -> None:
        """Should contain all code file extensions."""
        result = get_code_file_extensions()
        assert ".py" in result
        assert ".ts" in result
        assert ".go" in result
        assert ".rs" in result
        assert ".java" in result

    def test_excludes_config_extensions(self) -> None:
        """Should not contain config/data file extensions."""
        result = get_code_file_extensions()
        assert ".yaml" not in result
        assert ".yml" not in result
        assert ".json" not in result
        assert ".toml" not in result
        assert ".md" not in result

    def test_consistency_with_is_code_file(self) -> None:
        """get_code_file_extensions should match is_code_file for all registry entries."""
        code_extensions = get_code_file_extensions()
        for ext in LANGUAGE_REGISTRY:
            if is_code_file(ext):
                assert ext in code_extensions, f"{ext} should be in code extensions"
            else:
                assert ext not in code_extensions, f"{ext} should not be in code extensions"


class TestRegistryConsistency:
    """Tests to ensure the registry is internally consistent."""

    def test_all_code_extensions_have_semantic(self) -> None:
        """All code file extensions should have semantic language codes."""
        for ext, info in LANGUAGE_REGISTRY.items():
            if info.is_code:
                assert info.semantic != "txt", f"Code file {ext} should have specific semantic code"

    def test_cpp_family_consistency(self) -> None:
        """C++ extensions should all map to same semantic code."""
        cpp_extensions = [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"]
        semantics = {LANGUAGE_REGISTRY[ext].semantic for ext in cpp_extensions}
        assert len(semantics) == 1, f"C++ extensions should all have same semantic: {semantics}"
        assert "cpp" in semantics

    def test_shell_family_consistency(self) -> None:
        """Shell extensions should all map to same semantic code."""
        shell_extensions = [".sh", ".bash", ".zsh"]
        semantics = {LANGUAGE_REGISTRY[ext].semantic for ext in shell_extensions}
        assert len(semantics) == 1, f"Shell extensions should all have same semantic: {semantics}"
        assert "sh" in semantics

    def test_yaml_family_consistency(self) -> None:
        """YAML extensions should all map to same semantic code."""
        yaml_extensions = [".yaml", ".yml"]
        for ext in yaml_extensions:
            assert LANGUAGE_REGISTRY[ext].semantic == "txt"
            assert LANGUAGE_REGISTRY[ext].lexer == "yaml"
            assert LANGUAGE_REGISTRY[ext].is_code is False
