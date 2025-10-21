"""Tests for tree-sitter definition matcher."""

from dataclasses import dataclass

from ember.adapters.parsers.definition_matcher import DefinitionMatcher


# Mock tree-sitter Node for testing
@dataclass
class MockNode:
    """Mock tree-sitter Node for testing."""

    start_byte: int
    end_byte: int
    start_point: tuple[int, int]  # (row, column)
    end_point: tuple[int, int]  # (row, column)
    text: str | bytes
    parent: "MockNode | None" = None


def test_definition_matcher_empty_captures():
    """Test DefinitionMatcher handles empty captures."""
    captures = {}
    definitions = DefinitionMatcher.match(captures)
    assert definitions == []


def test_definition_matcher_no_definitions():
    """Test DefinitionMatcher handles captures with no definitions."""
    captures = {"other.capture": []}
    definitions = DefinitionMatcher.match(captures)
    assert definitions == []


def test_definition_matcher_single_named_definition():
    """Test DefinitionMatcher matches a single named definition."""
    # Create mock nodes
    def_node = MockNode(
        start_byte=0,
        end_byte=50,
        start_point=(0, 0),  # Line 1, column 0
        end_point=(2, 0),  # Line 3, column 0
        text=b"def foo():\n    pass",
    )

    name_node = MockNode(
        start_byte=4,
        end_byte=7,
        start_point=(0, 4),
        end_point=(0, 7),
        text=b"foo",
        parent=def_node,
    )

    captures = {"func.def": [def_node], "func.name": [name_node]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 1
    assert definitions[0].symbol == "foo"
    assert definitions[0].start_line == 1
    assert definitions[0].end_line == 3


def test_definition_matcher_unnamed_definition():
    """Test DefinitionMatcher handles definitions without names."""
    # Arrow function without explicit name
    def_node = MockNode(
        start_byte=0,
        end_byte=30,
        start_point=(4, 0),  # Line 5
        end_point=(6, 0),  # Line 7
        text=b"() => { return 42; }",
    )

    captures = {"arrow.def": [def_node]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 1
    assert definitions[0].symbol is None
    assert definitions[0].start_line == 5
    assert definitions[0].end_line == 7


def test_definition_matcher_multiple_definitions():
    """Test DefinitionMatcher handles multiple definitions."""
    # First function
    def_node1 = MockNode(
        start_byte=0,
        end_byte=30,
        start_point=(0, 0),
        end_point=(2, 0),
        text=b"def add():\n    pass",
    )
    name_node1 = MockNode(
        start_byte=4,
        end_byte=7,
        start_point=(0, 4),
        end_point=(0, 7),
        text=b"add",
        parent=def_node1,
    )

    # Second function
    def_node2 = MockNode(
        start_byte=40,
        end_byte=70,
        start_point=(4, 0),
        end_point=(6, 0),
        text=b"def multiply():\n    pass",
    )
    name_node2 = MockNode(
        start_byte=44,
        end_byte=52,
        start_point=(4, 4),
        end_point=(4, 12),
        text=b"multiply",
        parent=def_node2,
    )

    captures = {"func.def": [def_node1, def_node2], "func.name": [name_node1, name_node2]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 2

    # Should have both functions
    symbols = {d.symbol for d in definitions}
    assert "add" in symbols
    assert "multiply" in symbols


def test_definition_matcher_nested_definitions():
    """Test DefinitionMatcher handles nested class/method structures."""
    # Class definition
    class_node = MockNode(
        start_byte=0,
        end_byte=100,
        start_point=(0, 0),
        end_point=(9, 0),
        text=b"class Calculator:\n    def add(): pass",
    )
    class_name = MockNode(
        start_byte=6,
        end_byte=16,
        start_point=(0, 6),
        end_point=(0, 16),
        text=b"Calculator",
        parent=class_node,
    )

    # Method definition (nested inside class)
    method_node = MockNode(
        start_byte=20,
        end_byte=40,
        start_point=(1, 4),
        end_point=(1, 20),
        text=b"def add(): pass",
        parent=class_node,
    )
    method_name = MockNode(
        start_byte=24,
        end_byte=27,
        start_point=(1, 8),
        end_point=(1, 11),
        text=b"add",
        parent=method_node,
    )

    captures = {
        "class.def": [class_node],
        "class.name": [class_name],
        "method.def": [method_node],
        "method.name": [method_name],
    }

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 2

    # Find class and method
    class_def = next(d for d in definitions if d.symbol == "Calculator")
    method_def = next(d for d in definitions if d.symbol == "add")

    assert class_def.start_line == 1
    assert class_def.end_line == 10

    assert method_def.start_line == 2
    assert method_def.end_line == 2


def test_definition_matcher_text_decoding():
    """Test DefinitionMatcher handles both bytes and string text."""
    # Node with bytes text
    def_node1 = MockNode(
        start_byte=0, end_byte=20, start_point=(0, 0), end_point=(1, 0), text=b"def foo(): pass"
    )
    name_node1 = MockNode(
        start_byte=4,
        end_byte=7,
        start_point=(0, 4),
        end_point=(0, 7),
        text=b"foo",
        parent=def_node1,
    )

    # Node with string text (some tree-sitter bindings return strings)
    def_node2 = MockNode(
        start_byte=30, end_byte=50, start_point=(3, 0), end_point=(4, 0), text="def bar(): pass"
    )
    name_node2 = MockNode(
        start_byte=34,
        end_byte=37,
        start_point=(3, 4),
        end_point=(3, 7),
        text="bar",
        parent=def_node2,
    )

    captures = {"func.def": [def_node1, def_node2], "func.name": [name_node1, name_node2]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 2
    symbols = {d.symbol for d in definitions}
    assert "foo" in symbols
    assert "bar" in symbols


def test_definition_matcher_multiple_names_single_definition():
    """Test DefinitionMatcher handles multiple name captures for one definition."""
    # In some languages, constructor name might match both class name and method name
    def_node = MockNode(
        start_byte=0,
        end_byte=50,
        start_point=(0, 0),
        end_point=(2, 0),
        text=b"class Foo:\n    def __init__(self): pass",
    )

    # Multiple names that might match
    name_node1 = MockNode(
        start_byte=6, end_byte=9, start_point=(0, 6), end_point=(0, 9), text=b"Foo", parent=def_node
    )
    name_node2 = MockNode(
        start_byte=20,
        end_byte=28,
        start_point=(1, 8),
        end_point=(1, 16),
        text=b"__init__",
        parent=def_node,
    )

    captures = {"class.def": [def_node], "class.name": [name_node1, name_node2]}

    definitions = DefinitionMatcher.match(captures)

    # Should have one definition (the last matching name wins)
    assert len(definitions) == 1
    # The second name node should overwrite the first
    assert definitions[0].symbol == "__init__"


def test_definition_matcher_deep_nesting():
    """Test DefinitionMatcher handles deeply nested parent relationships."""
    # Deeply nested structure: outer -> middle -> inner -> name
    outer = MockNode(
        start_byte=0, end_byte=100, start_point=(0, 0), end_point=(10, 0), text=b"outer"
    )
    middle = MockNode(
        start_byte=10,
        end_byte=80,
        start_point=(1, 0),
        end_point=(8, 0),
        text=b"middle",
        parent=outer,
    )
    inner = MockNode(
        start_byte=20,
        end_byte=60,
        start_point=(2, 0),
        end_point=(6, 0),
        text=b"inner",
        parent=middle,
    )

    # Definition is the outer node
    # Name is deeply nested inside
    name_node = MockNode(
        start_byte=30,
        end_byte=40,
        start_point=(3, 0),
        end_point=(3, 10),
        text=b"test",
        parent=inner,
    )

    captures = {"func.def": [outer], "func.name": [name_node]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 1
    assert definitions[0].symbol == "test"


def test_definition_matcher_no_parent_match():
    """Test DefinitionMatcher handles orphaned name nodes gracefully."""
    # Definition node
    def_node = MockNode(
        start_byte=0, end_byte=50, start_point=(0, 0), end_point=(2, 0), text=b"def foo(): pass"
    )

    # Name node with no parent chain leading to def_node
    orphan_name = MockNode(
        start_byte=100,
        end_byte=110,
        start_point=(10, 0),
        end_point=(10, 10),
        text=b"orphan",
        parent=None,
    )

    captures = {"func.def": [def_node], "func.name": [orphan_name]}

    definitions = DefinitionMatcher.match(captures)

    # Should have one unnamed definition (orphan name couldn't match)
    assert len(definitions) == 1
    assert definitions[0].symbol is None


def test_definition_matcher_mixed_named_unnamed():
    """Test DefinitionMatcher handles mix of named and unnamed definitions."""
    # Named function
    named_def = MockNode(
        start_byte=0, end_byte=30, start_point=(0, 0), end_point=(2, 0), text=b"def foo(): pass"
    )
    name_node = MockNode(
        start_byte=4,
        end_byte=7,
        start_point=(0, 4),
        end_point=(0, 7),
        text=b"foo",
        parent=named_def,
    )

    # Unnamed arrow function
    unnamed_def = MockNode(
        start_byte=40,
        end_byte=60,
        start_point=(4, 0),
        end_point=(4, 20),
        text=b"() => { return 42; }",
    )

    captures = {"func.def": [named_def], "arrow.def": [unnamed_def], "func.name": [name_node]}

    definitions = DefinitionMatcher.match(captures)

    assert len(definitions) == 2

    # One should be named, one unnamed
    named = [d for d in definitions if d.symbol is not None]
    unnamed = [d for d in definitions if d.symbol is None]

    assert len(named) == 1
    assert len(unnamed) == 1
    assert named[0].symbol == "foo"
