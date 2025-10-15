"""Tree-sitter based code-aware chunker.

Extracts semantic code units (functions, classes, methods) using tree-sitter AST parsing.
"""

from pathlib import Path

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

from ember.ports.chunkers import ChunkData


class TreeSitterChunker:
    """Code-aware chunker using tree-sitter for AST-based extraction.

    Supports Python, TypeScript, JavaScript, Go, Rust, Java, C/C++, C#, and Ruby.
    Extracts functions, methods, and classes as semantic chunks.
    """

    # Map of language identifiers to (lang_name, lang_module, lang_function)
    # lang_function is the function name to call on the module to get the Language object
    _LANG_MAP = {
        "py": ("python", tree_sitter_python, "language"),
        "python": ("python", tree_sitter_python, "language"),
        "ts": ("typescript", tree_sitter_typescript, "language_typescript"),
        "tsx": ("tsx", tree_sitter_typescript, "language_tsx"),
        "typescript": ("typescript", tree_sitter_typescript, "language_typescript"),
        "js": ("javascript", tree_sitter_typescript, "language_typescript"),
        "jsx": ("jsx", tree_sitter_typescript, "language_tsx"),
        "javascript": ("javascript", tree_sitter_typescript, "language_typescript"),
        "go": ("go", tree_sitter_go, "language"),
        "rs": ("rust", tree_sitter_rust, "language"),
        "rust": ("rust", tree_sitter_rust, "language"),
        "java": ("java", tree_sitter_java, "language"),
        "c": ("c", tree_sitter_c, "language"),
        "cpp": ("cpp", tree_sitter_cpp, "language"),
        "cc": ("cpp", tree_sitter_cpp, "language"),
        "cxx": ("cpp", tree_sitter_cpp, "language"),
        "c++": ("cpp", tree_sitter_cpp, "language"),
        "h": ("c", tree_sitter_c, "language"),
        "hpp": ("cpp", tree_sitter_cpp, "language"),
        "cs": ("csharp", tree_sitter_c_sharp, "language"),
        "csharp": ("csharp", tree_sitter_c_sharp, "language"),
        "rb": ("ruby", tree_sitter_ruby, "language"),
        "ruby": ("ruby", tree_sitter_ruby, "language"),
    }

    # Tree-sitter query patterns for extracting definitions
    # Maps language name to query string for extracting top-level symbols
    _QUERIES = {
        "python": """
            (function_definition
                name: (identifier) @func.name) @func.def
            (class_definition
                name: (identifier) @class.name) @class.def
        """,
        "typescript": """
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (arrow_function) @arrow.def
        """,
        "tsx": """
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (type_identifier) @class.name) @class.def
            (arrow_function) @arrow.def
        """,
        "javascript": """
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (identifier) @class.name) @class.def
            (arrow_function) @arrow.def
        """,
        "jsx": """
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_definition
                name: (property_identifier) @method.name) @method.def
            (class_declaration
                name: (identifier) @class.name) @class.def
            (arrow_function) @arrow.def
        """,
        "go": """
            (function_declaration
                name: (identifier) @func.name) @func.def
            (method_declaration
                name: (field_identifier) @method.name) @method.def
        """,
        "rust": """
            (function_item
                name: (identifier) @func.name) @func.def
            (impl_item) @impl.def
        """,
        "java": """
            (class_declaration
                name: (identifier) @class.name) @class.def
            (interface_declaration
                name: (identifier) @interface.name) @interface.def
            (method_declaration
                name: (identifier) @method.name) @method.def
            (constructor_declaration
                name: (identifier) @constructor.name) @constructor.def
        """,
        "c": """
            (function_definition
                declarator: (function_declarator
                    declarator: (identifier) @func.name)) @func.def
            (struct_specifier
                name: (type_identifier) @struct.name) @struct.def
        """,
        "cpp": """
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
        "csharp": """
            (class_declaration
                name: (identifier) @class.name) @class.def
            (interface_declaration
                name: (identifier) @interface.name) @interface.def
            (method_declaration
                name: (identifier) @method.name) @method.def
            (constructor_declaration
                name: (identifier) @constructor.name) @constructor.def
        """,
        "ruby": """
            (method
                name: (identifier) @method.name) @method.def
            (singleton_method
                name: (identifier) @method.name) @method.def
            (class
                name: (constant) @class.name) @class.def
            (module
                name: (constant) @module.name) @module.def
        """,
    }

    def __init__(self) -> None:
        """Initialize tree-sitter chunker with language parsers."""
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}

        # Initialize parsers for each supported language
        for lang_id, (lang_name, lang_module, lang_func_name) in self._LANG_MAP.items():
            if lang_name not in self._languages:
                # Get the language from the module by calling the appropriate function
                lang_func = getattr(lang_module, lang_func_name)
                lang = Language(lang_func())
                self._languages[lang_name] = lang

                # Create a parser for this language
                parser = Parser(lang)
                self._parsers[lang_name] = parser

    @property
    def supported_languages(self) -> set[str]:
        """Return set of supported language identifiers."""
        return set(self._LANG_MAP.keys())

    def chunk_file(self, content: str, path: Path, lang: str) -> list[ChunkData]:
        """Chunk file using tree-sitter AST parsing.

        Args:
            content: File content as string.
            path: File path (for context).
            lang: Language identifier.

        Returns:
            List of ChunkData for extracted functions/classes.
            Empty list if language not supported or parsing fails.
        """
        # Check if language is supported
        if lang not in self._LANG_MAP:
            return []

        lang_name, _, _ = self._LANG_MAP[lang]
        parser = self._parsers.get(lang_name)
        language = self._languages.get(lang_name)

        if not parser or not language:
            return []

        # Parse the content
        try:
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            # Parsing failed, return empty list
            return []

        # Get query for this language
        query_string = self._QUERIES.get(lang_name)
        if not query_string:
            return []

        # Execute query to find definitions
        try:
            from tree_sitter import Query, QueryCursor

            query = Query(language, query_string)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
        except Exception:
            # Query execution failed
            return []

        # Extract chunks from captures
        # New API returns dict: {capture_name: [nodes]}
        chunks: list[ChunkData] = []
        content_lines = content.split("\n")

        # Get definition nodes and name nodes
        def_nodes = []
        name_nodes = []

        for capture_name, nodes in captures.items():
            if capture_name.endswith(".def"):
                def_nodes.extend(nodes)
            elif capture_name.endswith(".name"):
                name_nodes.extend(nodes)

        # Match names to their definitions using byte positions
        # Key is (start_byte, end_byte) to uniquely identify nodes
        definitions: dict[tuple[int, int], tuple[str | None, int, int]] = {}

        # First, create entries for all definitions
        for def_node in def_nodes:
            node_key = (def_node.start_byte, def_node.end_byte)
            start_line = def_node.start_point[0] + 1  # tree-sitter is 0-indexed
            end_line = def_node.end_point[0] + 1
            definitions[node_key] = (None, start_line, end_line)

        # Then, find the names for each definition
        for name_node in name_nodes:
            symbol_name = name_node.text.decode("utf-8") if isinstance(name_node.text, bytes) else name_node.text
            # Find the parent definition node by walking up and checking byte positions
            parent = name_node.parent
            while parent:
                parent_key = (parent.start_byte, parent.end_byte)
                if parent_key in definitions:
                    # Update with name
                    _, start, end = definitions[parent_key]
                    definitions[parent_key] = (symbol_name, start, end)
                    break
                parent = parent.parent

        # Create ChunkData for each definition
        for symbol_name, start_line, end_line in definitions.values():
            # Extract content for this range
            chunk_lines = content_lines[start_line - 1 : end_line]
            chunk_content = "\n".join(chunk_lines)

            chunks.append(
                ChunkData(
                    start_line=start_line,
                    end_line=end_line,
                    content=chunk_content,
                    symbol=symbol_name,
                    lang=lang,
                )
            )

        # Sort chunks by start line
        chunks.sort(key=lambda c: c.start_line)

        return chunks
