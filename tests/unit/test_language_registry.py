"""Tests for tree-sitter language registry."""

from ember.adapters.parsers.language_registry import LanguageConfig, LanguageRegistry


def test_language_registry_initialization():
    """Test language registry initializes successfully."""
    registry = LanguageRegistry()
    assert registry is not None


def test_language_registry_supported_identifiers():
    """Test language registry provides all supported identifiers."""
    registry = LanguageRegistry()
    identifiers = registry.supported_identifiers

    # Should include file extensions and aliases
    assert "py" in identifiers
    assert "python" in identifiers
    assert "ts" in identifiers
    assert "js" in identifiers
    assert "go" in identifiers
    assert "rs" in identifiers
    assert "rust" in identifiers
    assert "java" in identifiers
    assert "c" in identifiers
    assert "cpp" in identifiers
    assert "cs" in identifiers
    assert "rb" in identifiers


def test_get_by_identifier_python():
    """Test retrieving language config by identifier for Python."""
    registry = LanguageRegistry()

    # Test with file extension
    config = registry.get_by_identifier("py")
    assert config is not None
    assert config.name == "python"
    assert "py" in config.identifiers
    assert "python" in config.identifiers
    assert "function_definition" in config.query

    # Test with language name alias
    config_alias = registry.get_by_identifier("python")
    assert config_alias is not None
    assert config_alias.name == "python"


def test_get_by_identifier_typescript():
    """Test retrieving language config by identifier for TypeScript."""
    registry = LanguageRegistry()

    config = registry.get_by_identifier("ts")
    assert config is not None
    assert config.name == "typescript"
    assert "ts" in config.identifiers
    assert "typescript" in config.identifiers


def test_get_by_identifier_unsupported():
    """Test retrieving unsupported language returns None."""
    registry = LanguageRegistry()

    config = registry.get_by_identifier("sql")
    assert config is None


def test_get_by_name_python():
    """Test retrieving language config by canonical name."""
    registry = LanguageRegistry()

    config = registry.get_by_name("python")
    assert config is not None
    assert config.name == "python"
    assert config.module_func == "language"


def test_get_by_name_unsupported():
    """Test retrieving unsupported language by name returns None."""
    registry = LanguageRegistry()

    config = registry.get_by_name("kotlin")
    assert config is None


def test_get_language_lazy_initialization():
    """Test language objects are lazily initialized."""
    registry = LanguageRegistry()

    # Cache should be empty initially
    assert len(registry._language_cache) == 0

    # First access initializes language
    lang = registry.get_language("python")
    assert lang is not None
    assert "python" in registry._language_cache

    # Second access uses cache
    lang2 = registry.get_language("python")
    assert lang2 is lang  # Same object from cache


def test_get_parser_lazy_initialization():
    """Test parser objects are lazily initialized."""
    registry = LanguageRegistry()

    # Cache should be empty initially
    assert len(registry._parser_cache) == 0

    # First access initializes parser
    parser = registry.get_parser("python")
    assert parser is not None
    assert "python" in registry._parser_cache

    # Second access uses cache
    parser2 = registry.get_parser("python")
    assert parser2 is parser  # Same object from cache


def test_get_parser_also_initializes_language():
    """Test getting parser also initializes language object."""
    registry = LanguageRegistry()

    # Get parser (should also initialize language)
    parser = registry.get_parser("python")
    assert parser is not None

    # Language should also be cached
    assert "python" in registry._language_cache


def test_get_language_unsupported():
    """Test getting language for unsupported name returns None."""
    registry = LanguageRegistry()

    lang = registry.get_language("fortran")
    assert lang is None


def test_get_parser_unsupported():
    """Test getting parser for unsupported name returns None."""
    registry = LanguageRegistry()

    parser = registry.get_parser("fortran")
    assert parser is None


def test_language_config_structure():
    """Test language config has expected structure."""
    registry = LanguageRegistry()

    config = registry.get_by_name("python")
    assert config is not None

    # Check all required fields
    assert isinstance(config.name, str)
    assert config.module is not None
    assert isinstance(config.module_func, str)
    assert isinstance(config.identifiers, list)
    assert len(config.identifiers) > 0
    assert isinstance(config.query, str)
    assert len(config.query) > 0


def test_multiple_identifiers_same_language():
    """Test multiple identifiers map to same language config."""
    registry = LanguageRegistry()

    config_py = registry.get_by_identifier("py")
    config_python = registry.get_by_identifier("python")

    assert config_py is config_python  # Same config object


def test_all_languages_have_queries():
    """Test all registered languages have query strings."""
    registry = LanguageRegistry()

    for identifier in registry.supported_identifiers:
        config = registry.get_by_identifier(identifier)
        assert config is not None
        assert config.query is not None
        assert len(config.query.strip()) > 0


def test_cpp_identifiers():
    """Test C++ has all expected file extensions."""
    registry = LanguageRegistry()

    cpp_config = registry.get_by_name("cpp")
    assert cpp_config is not None

    # Should support multiple C++ extensions
    assert "cpp" in cpp_config.identifiers
    assert "cc" in cpp_config.identifiers
    assert "cxx" in cpp_config.identifiers
    assert "c++" in cpp_config.identifiers
    assert "hpp" in cpp_config.identifiers


def test_javascript_tsx_separate_configs():
    """Test JavaScript and TypeScript variants have separate configs."""
    registry = LanguageRegistry()

    js_config = registry.get_by_identifier("js")
    jsx_config = registry.get_by_identifier("jsx")
    ts_config = registry.get_by_identifier("ts")
    tsx_config = registry.get_by_identifier("tsx")

    # All should exist
    assert js_config is not None
    assert jsx_config is not None
    assert ts_config is not None
    assert tsx_config is not None

    # Should be different configs
    assert js_config.name == "javascript"
    assert jsx_config.name == "jsx"
    assert ts_config.name == "typescript"
    assert tsx_config.name == "tsx"


def test_lazy_init_memory_efficiency():
    """Test lazy initialization saves memory for unused languages."""
    registry = LanguageRegistry()

    # Initially no parsers loaded
    assert len(registry._parser_cache) == 0
    assert len(registry._language_cache) == 0

    # Load only Python
    registry.get_parser("python")

    # Only Python should be cached
    assert len(registry._parser_cache) == 1
    assert len(registry._language_cache) == 1
    assert "python" in registry._parser_cache

    # Other languages not loaded
    assert "go" not in registry._parser_cache
    assert "rust" not in registry._parser_cache
