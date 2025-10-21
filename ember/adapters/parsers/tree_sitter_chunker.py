"""Tree-sitter based code-aware chunker.

Extracts semantic code units (functions, classes, methods) using tree-sitter AST parsing.
"""

from pathlib import Path

from tree_sitter import Query, QueryCursor

from ember.adapters.parsers.language_registry import LanguageRegistry
from ember.ports.chunkers import ChunkData


class TreeSitterChunker:
    """Code-aware chunker using tree-sitter for AST-based extraction.

    Supports Python, TypeScript, JavaScript, Go, Rust, Java, C/C++, C#, and Ruby.
    Extracts functions, methods, and classes as semantic chunks.
    """

    def __init__(self) -> None:
        """Initialize tree-sitter chunker with language registry."""
        self._registry = LanguageRegistry()

    @property
    def supported_languages(self) -> set[str]:
        """Return set of supported language identifiers."""
        return self._registry.supported_identifiers

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
        # Get language configuration
        config = self._registry.get_by_identifier(lang)
        if not config:
            return []

        # Get parser and language (lazy initialization)
        parser = self._registry.get_parser(config.name)
        language = self._registry.get_language(config.name)

        if not parser or not language:
            return []

        # Parse the content
        try:
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception:
            # Parsing failed, return empty list
            return []

        # Execute query to find definitions
        try:
            query = Query(language, config.query)
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
