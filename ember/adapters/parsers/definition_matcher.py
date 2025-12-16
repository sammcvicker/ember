"""Matches tree-sitter name nodes to their parent definition nodes.

Handles the complex logic of associating captured names (e.g., function names)
with their parent definition nodes (e.g., function_definition) in the AST.
"""

from dataclasses import dataclass


@dataclass
class Definition:
    """Represents a matched code definition with its location and name.

    Attributes:
        symbol: The name of the definition (e.g., function/class name), or None if unnamed.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (1-indexed).
    """

    symbol: str | None
    start_line: int
    end_line: int


class DefinitionMatcher:
    """Matches tree-sitter name captures to their parent definition captures.

    Tree-sitter queries return two types of captures:
    - Definition nodes (e.g., @func.def, @class.def) - structural nodes
    - Name nodes (e.g., @func.name, @class.name) - identifier nodes

    This class matches each name to its parent definition by walking up the AST tree.
    """

    @staticmethod
    def match(captures: dict[str, list]) -> list[Definition]:
        """Match name nodes to their parent definition nodes.

        Args:
            captures: Dict from tree-sitter QueryCursor.captures().
                     Maps capture names to lists of matched nodes.

        Returns:
            List of Definition objects with matched names and locations.
            Unnamed definitions (no matching name node) will have symbol=None.

        Algorithm:
            1. Separate captures into def_nodes and name_nodes
            2. Create entries for all definition nodes with byte positions
            3. For each name node, walk up AST to find parent definition (with memoization)
            4. Return matched definitions with line numbers

        Complexity: O(n + m) where n = total nodes, m = name nodes
            - Each AST node is visited at most once due to memoization
            - Previous O(n*m) algorithm revisited parent nodes repeatedly
        """
        # Separate definition nodes from name nodes
        def_nodes = []
        name_nodes = []

        for capture_name, nodes in captures.items():
            if capture_name.endswith(".def"):
                def_nodes.extend(nodes)
            elif capture_name.endswith(".name"):
                name_nodes.extend(nodes)

        # Build map of definition nodes keyed by byte position
        # Key: (start_byte, end_byte) uniquely identifies a node
        # Value: (symbol_name, start_line, end_line)
        definitions: dict[tuple[int, int], tuple[str | None, int, int]] = {}

        # Build set of definition positions for O(1) membership check
        definition_positions: set[tuple[int, int]] = set()

        # First pass: create entries for all definitions
        for def_node in def_nodes:
            node_key = (def_node.start_byte, def_node.end_byte)
            start_line = def_node.start_point[0] + 1  # tree-sitter is 0-indexed
            end_line = def_node.end_point[0] + 1
            definitions[node_key] = (None, start_line, end_line)
            definition_positions.add(node_key)

        # Memoization cache: maps node position -> nearest ancestor definition position (or None)
        # This avoids re-traversing the same parent paths for multiple name nodes
        ancestor_cache: dict[tuple[int, int], tuple[int, int] | None] = {}

        def find_definition_ancestor(node) -> tuple[int, int] | None:
            """Find the nearest ancestor that is a definition node, with memoization."""
            if node is None:
                return None

            node_key = (node.start_byte, node.end_byte)

            # Check cache first
            if node_key in ancestor_cache:
                return ancestor_cache[node_key]

            # Check if this node itself is a definition
            if node_key in definition_positions:
                ancestor_cache[node_key] = node_key
                return node_key

            # Recursively check parent (will be cached on the way back up)
            result = find_definition_ancestor(node.parent)
            ancestor_cache[node_key] = result
            return result

        # Second pass: match names to their parent definitions
        for name_node in name_nodes:
            # Find ancestor definition using memoized lookup
            def_key = find_definition_ancestor(name_node.parent)

            if def_key is not None:
                # Decode name text
                symbol_name = (
                    name_node.text.decode("utf-8")
                    if isinstance(name_node.text, bytes)
                    else name_node.text
                )
                # Update definition with name
                _, start, end = definitions[def_key]
                definitions[def_key] = (symbol_name, start, end)

        # Convert to Definition objects
        return [
            Definition(symbol=symbol, start_line=start, end_line=end)
            for symbol, start, end in definitions.values()
        ]
