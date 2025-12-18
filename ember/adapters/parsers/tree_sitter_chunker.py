"""Tree-sitter based code-aware chunker.

Extracts semantic code units (functions, classes, methods) using tree-sitter AST parsing.
"""

import logging
from pathlib import Path

from tree_sitter import Query, QueryCursor

from ember.adapters.parsers.definition_matcher import DefinitionMatcher
from ember.adapters.parsers.language_registry import LanguageRegistry
from ember.ports.chunkers import ChunkData

logger = logging.getLogger(__name__)


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
            logger.debug(f"Language '{lang}' not supported by tree-sitter chunker (file: {path})")
            return []

        # Get parser and language (lazy initialization)
        parser = self._registry.get_parser(config.name)
        language = self._registry.get_language(config.name)

        if not parser or not language:
            logger.warning(f"Failed to initialize parser for {config.name} (file: {path})")
            return []

        # Parse the content
        try:
            tree = parser.parse(bytes(content, "utf-8"))
        except UnicodeEncodeError as e:
            logger.warning(f"Failed to encode {path} as UTF-8: {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to parse {path} as {config.name}: {e}")
            return []

        # Execute query to find definitions
        try:
            query = Query(language, config.query)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)
        except Exception as e:
            logger.warning(f"Query execution failed for {path} ({config.name}): {e}")
            return []

        # Match names to definitions using DefinitionMatcher
        definitions = DefinitionMatcher.match(captures)

        if not definitions:
            logger.debug(f"No definitions found in {path} ({config.name})")
            return []

        # Create ChunkData for each definition
        content_lines = content.split("\n")
        chunks: list[ChunkData] = []

        for definition in definitions:
            # Extract content for this range
            chunk_lines = content_lines[definition.start_line - 1 : definition.end_line]
            chunk_content = "\n".join(chunk_lines)

            chunks.append(
                ChunkData(
                    start_line=definition.start_line,
                    end_line=definition.end_line,
                    content=chunk_content,
                    symbol=definition.symbol,
                    lang=lang,
                )
            )

        # Sort chunks by start line
        chunks.sort(key=lambda c: c.start_line)

        logger.debug(f"Extracted {len(chunks)} chunks from {path} ({config.name})")
        return chunks
