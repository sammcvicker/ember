"""Registry for tree-sitter language configurations.

Provides centralized configuration and lazy initialization for supported languages.
"""

from dataclasses import dataclass
from typing import Any

import tree_sitter_c
import tree_sitter_c_sharp
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_python
import tree_sitter_ruby
import tree_sitter_rust
import tree_sitter_typescript
from tree_sitter import Language, Parser


@dataclass
class LanguageConfig:
    """Configuration for a tree-sitter supported language.

    Attributes:
        name: Canonical language name (e.g., "python", "typescript").
        module: tree-sitter module containing language parser.
        module_func: Function name to call on module to get language.
        identifiers: List of file extensions and aliases (e.g., ["py", "python"]).
        query: Tree-sitter query string for extracting code definitions.
    """

    name: str
    module: Any
    module_func: str
    identifiers: list[str]
    query: str


class LanguageRegistry:
    """Registry for tree-sitter language configurations.

    Provides:
    - Single source of truth for language configurations
    - Lazy initialization of parsers (load on first use)
    - Lookup by extension or canonical name
    """

    # Language configurations
    _CONFIGS = [
        LanguageConfig(
            name="python",
            module=tree_sitter_python,
            module_func="language",
            identifiers=["py", "python"],
            query="""
            (function_definition
                name: (identifier) @func.name) @func.def
            (class_definition
                name: (identifier) @class.name) @class.def
        """,
        ),
        LanguageConfig(
            name="typescript",
            module=tree_sitter_typescript,
            module_func="language_typescript",
            identifiers=["ts", "typescript"],
            query="""
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (interface_declaration
                name: (type_identifier) @interface.name) @interface.def
            (type_alias_declaration
                name: (type_identifier) @type.name) @type.def
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
            (variable_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
        """,
        ),
        LanguageConfig(
            name="tsx",
            module=tree_sitter_typescript,
            module_func="language_tsx",
            identifiers=["tsx"],
            query="""
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (interface_declaration
                name: (type_identifier) @interface.name) @interface.def
            (type_alias_declaration
                name: (type_identifier) @type.name) @type.def
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
            (variable_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
        """,
        ),
        LanguageConfig(
            name="javascript",
            module=tree_sitter_typescript,
            module_func="language_typescript",
            identifiers=["js", "javascript"],
            query="""
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
            (variable_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
        """,
        ),
        LanguageConfig(
            name="jsx",
            module=tree_sitter_typescript,
            module_func="language_tsx",
            identifiers=["jsx"],
            query="""
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (lexical_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
            (variable_declaration
                (variable_declarator
                    name: (identifier) @arrow.name
                    value: (arrow_function))) @arrow.def
        """,
        ),
        LanguageConfig(
            name="go",
            module=tree_sitter_go,
            module_func="language",
            identifiers=["go"],
            query="""
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_declaration
                name: (field_identifier) @method.name) @method.def
            (type_declaration
                (type_spec
                    name: (type_identifier) @struct.name
                    type: (struct_type))) @struct.def
            (type_declaration
                (type_spec
                    name: (type_identifier) @interface.name
                    type: (interface_type))) @interface.def
        """,
        ),
        LanguageConfig(
            name="rust",
            module=tree_sitter_rust,
            module_func="language",
            identifiers=["rs", "rust"],
            query="""
            (function_item
                name: (identifier) @func.name) @func.def
            (impl_item) @impl.def
            (struct_item
                name: (type_identifier) @struct.name) @struct.def
            (enum_item
                name: (type_identifier) @enum.name) @enum.def
            (trait_item
                name: (type_identifier) @trait.name) @trait.def
        """,
        ),
        LanguageConfig(
            name="java",
            module=tree_sitter_java,
            module_func="language",
            identifiers=["java"],
            query="""
            (class_declaration
                name: (identifier) @class.name) @class.def
            (interface_declaration
                name: (identifier) @interface.name) @interface.def
            (method_declaration
                name: (identifier) @method.name) @method.def
            (constructor_declaration
                name: (identifier) @constructor.name) @constructor.def
        """,
        ),
        LanguageConfig(
            name="c",
            module=tree_sitter_c,
            module_func="language",
            identifiers=["c", "h"],
            query="""
            (function_definition
                declarator: (function_declarator
                    declarator: (identifier) @func.name)) @func.def
            (struct_specifier
                name: (type_identifier) @struct.name) @struct.def
        """,
        ),
        LanguageConfig(
            name="cpp",
            module=tree_sitter_cpp,
            module_func="language",
            identifiers=["cpp", "cc", "cxx", "c++", "hpp"],
            query="""
            (function_definition
                declarator: (function_declarator
                    declarator: (identifier) @func.name)) @func.def
            (function_definition
                declarator: (function_declarator
                    declarator: (qualified_identifier
                        name: (identifier) @method.name))) @method.def
            (class_specifier
                name: (type_identifier) @class.name) @class.def
            (struct_specifier
                name: (type_identifier) @struct.name) @struct.def
        """,
        ),
        LanguageConfig(
            name="csharp",
            module=tree_sitter_c_sharp,
            module_func="language",
            identifiers=["cs", "csharp"],
            query="""
            (class_declaration
                name: (identifier) @class.name) @class.def
            (interface_declaration
                name: (identifier) @interface.name) @interface.def
            (method_declaration
                name: (identifier) @method.name) @method.def
            (constructor_declaration
                name: (identifier) @constructor.name) @constructor.def
        """,
        ),
        LanguageConfig(
            name="ruby",
            module=tree_sitter_ruby,
            module_func="language",
            identifiers=["rb", "ruby"],
            query="""
            (method
                name: (identifier) @method.name) @method.def
            (singleton_method
                name: (identifier) @method.name) @method.def
            (class
                name: (constant) @class.name) @class.def
            (module
                name: (constant) @module.name) @module.def
        """,
        ),
    ]

    def __init__(self) -> None:
        """Initialize the language registry."""
        # Build lookup maps
        self._by_name: dict[str, LanguageConfig] = {cfg.name: cfg for cfg in self._CONFIGS}
        self._by_identifier: dict[str, LanguageConfig] = {}
        for cfg in self._CONFIGS:
            for identifier in cfg.identifiers:
                self._by_identifier[identifier] = cfg

        # Lazy initialization caches
        self._language_cache: dict[str, Language] = {}
        self._parser_cache: dict[str, Parser] = {}

    @property
    def supported_identifiers(self) -> set[str]:
        """Return set of all supported language identifiers (extensions and aliases)."""
        return set(self._by_identifier.keys())

    def get_by_identifier(self, identifier: str) -> LanguageConfig | None:
        """Get language config by file extension or alias.

        Args:
            identifier: File extension (e.g., "py") or alias (e.g., "python").

        Returns:
            LanguageConfig if found, None otherwise.
        """
        return self._by_identifier.get(identifier)

    def get_by_name(self, name: str) -> LanguageConfig | None:
        """Get language config by canonical name.

        Args:
            name: Canonical language name (e.g., "python", "typescript").

        Returns:
            LanguageConfig if found, None otherwise.
        """
        return self._by_name.get(name)

    def get_language(self, name: str) -> Language | None:
        """Get tree-sitter Language object for a language (lazy initialization).

        Args:
            name: Canonical language name.

        Returns:
            Language object if found, None otherwise.
        """
        if name in self._language_cache:
            return self._language_cache[name]

        config = self.get_by_name(name)
        if not config:
            return None

        # Initialize language
        lang_func = getattr(config.module, config.module_func)
        language = Language(lang_func())
        self._language_cache[name] = language
        return language

    def get_parser(self, name: str) -> Parser | None:
        """Get tree-sitter Parser for a language (lazy initialization).

        Args:
            name: Canonical language name.

        Returns:
            Parser object if found, None otherwise.
        """
        if name in self._parser_cache:
            return self._parser_cache[name]

        language = self.get_language(name)
        if not language:
            return None

        # Initialize parser
        parser = Parser(language)
        self._parser_cache[name] = parser
        return parser
