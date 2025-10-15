"""Tests for tree-sitter based code-aware chunker."""

from pathlib import Path

from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker


def test_tree_sitter_initialization():
    """Test tree-sitter chunker initializes successfully."""
    chunker = TreeSitterChunker()
    assert chunker is not None


def test_tree_sitter_supported_languages():
    """Test tree-sitter chunker supports expected languages."""
    chunker = TreeSitterChunker()
    supported = chunker.supported_languages

    # Should support Python, TypeScript, JavaScript, Go, Rust
    assert "py" in supported
    assert "python" in supported
    assert "ts" in supported
    assert "tsx" in supported
    assert "js" in supported
    assert "jsx" in supported
    assert "go" in supported
    assert "rs" in supported
    assert "rust" in supported


def test_tree_sitter_unsupported_language():
    """Test tree-sitter chunker returns empty for unsupported language."""
    chunker = TreeSitterChunker()
    content = "SELECT * FROM users;"

    chunks = chunker.chunk_file(content, Path("query.sql"), "sql")

    assert chunks == []


def test_tree_sitter_empty_content():
    """Test tree-sitter chunker handles empty content."""
    chunker = TreeSitterChunker()
    chunks = chunker.chunk_file("", Path("test.py"), "py")
    assert chunks == []


def test_tree_sitter_python_functions():
    """Test tree-sitter extracts Python functions."""
    chunker = TreeSitterChunker()
    content = """def add(a, b):
    '''Add two numbers.'''
    return a + b

def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b

def divide(a, b):
    '''Divide two numbers.'''
    if b == 0:
        raise ValueError("Division by zero")
    return a / b
"""

    chunks = chunker.chunk_file(content, Path("math.py"), "py")

    # Should extract 3 functions
    assert len(chunks) == 3

    # Check first function
    assert chunks[0].symbol == "add"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3
    assert "def add(a, b):" in chunks[0].content
    assert chunks[0].lang == "py"

    # Check second function
    assert chunks[1].symbol == "multiply"
    assert chunks[1].start_line == 5
    assert chunks[1].end_line == 7

    # Check third function
    assert chunks[2].symbol == "divide"
    assert chunks[2].start_line == 9
    assert chunks[2].end_line == 13


def test_tree_sitter_python_classes():
    """Test tree-sitter extracts Python classes."""
    chunker = TreeSitterChunker()
    content = """class Calculator:
    '''A simple calculator.'''

    def __init__(self):
        self.result = 0

    def add(self, x):
        self.result += x
        return self.result

class ScientificCalculator(Calculator):
    '''Scientific calculator with more functions.'''

    def power(self, x, y):
        return x ** y
"""

    chunks = chunker.chunk_file(content, Path("calc.py"), "py")

    # Should extract 2 classes + 3 methods = 5 total chunks
    # Tree-sitter extracts both class definitions and nested method definitions
    assert len(chunks) == 5

    # Find class chunks
    class_chunks = [c for c in chunks if c.symbol in ("Calculator", "ScientificCalculator")]
    assert len(class_chunks) == 2

    # Check first class
    assert class_chunks[0].symbol == "Calculator"
    assert class_chunks[0].start_line == 1
    assert "class Calculator:" in class_chunks[0].content

    # Check second class
    assert class_chunks[1].symbol == "ScientificCalculator"
    assert "class ScientificCalculator" in class_chunks[1].content

    # Verify methods were also extracted
    method_symbols = {c.symbol for c in chunks if c.symbol not in ("Calculator", "ScientificCalculator")}
    assert "__init__" in method_symbols
    assert "add" in method_symbols
    assert "power" in method_symbols


def test_tree_sitter_typescript_functions():
    """Test tree-sitter extracts TypeScript functions."""
    chunker = TreeSitterChunker()
    content = """function greet(name: string): string {
    return `Hello, ${name}!`;
}

function add(a: number, b: number): number {
    return a + b;
}

const multiply = (a: number, b: number): number => {
    return a * b;
};
"""

    chunks = chunker.chunk_file(content, Path("utils.ts"), "ts")

    # Should extract functions (at least named functions)
    assert len(chunks) >= 2

    # Find the greet function
    greet_chunks = [c for c in chunks if c.symbol == "greet"]
    assert len(greet_chunks) == 1
    assert "function greet" in greet_chunks[0].content

    # Find the add function
    add_chunks = [c for c in chunks if c.symbol == "add"]
    assert len(add_chunks) == 1
    assert "function add" in add_chunks[0].content


def test_tree_sitter_typescript_classes():
    """Test tree-sitter extracts TypeScript classes."""
    chunker = TreeSitterChunker()
    content = """class User {
    constructor(public name: string, public age: number) {}

    greet(): string {
        return `Hello, I'm ${this.name}`;
    }
}

class Admin extends User {
    constructor(name: string, age: number, public role: string) {
        super(name, age);
    }
}
"""

    chunks = chunker.chunk_file(content, Path("user.ts"), "ts")

    # Should extract 2 classes
    assert len(chunks) >= 2

    # Find User class
    user_chunks = [c for c in chunks if c.symbol == "User"]
    assert len(user_chunks) == 1
    assert "class User" in user_chunks[0].content


def test_tree_sitter_go_functions():
    """Test tree-sitter extracts Go functions."""
    chunker = TreeSitterChunker()
    content = """package main

func add(a int, b int) int {
    return a + b
}

func multiply(a, b int) int {
    return a * b
}
"""

    chunks = chunker.chunk_file(content, Path("math.go"), "go")

    # Should extract 2 functions
    assert len(chunks) == 2

    # Check functions
    symbols = {c.symbol for c in chunks}
    assert "add" in symbols
    assert "multiply" in symbols


def test_tree_sitter_rust_functions():
    """Test tree-sitter extracts Rust functions."""
    chunker = TreeSitterChunker()
    content = """fn add(a: i32, b: i32) -> i32 {
    a + b
}

fn multiply(a: i32, b: i32) -> i32 {
    a * b
}

pub fn divide(a: i32, b: i32) -> Result<i32, String> {
    if b == 0 {
        Err("Division by zero".to_string())
    } else {
        Ok(a / b)
    }
}
"""

    chunks = chunker.chunk_file(content, Path("math.rs"), "rs")

    # Should extract 3 functions
    assert len(chunks) == 3

    # Check function symbols
    symbols = {c.symbol for c in chunks}
    assert "add" in symbols
    assert "multiply" in symbols
    assert "divide" in symbols


def test_tree_sitter_chunks_sorted_by_line():
    """Test tree-sitter returns chunks sorted by line number."""
    chunker = TreeSitterChunker()
    content = """def zebra():
    pass

def alpha():
    pass

def beta():
    pass
"""

    chunks = chunker.chunk_file(content, Path("test.py"), "py")

    # Should be sorted by line number, not alphabetically
    assert len(chunks) == 3
    assert chunks[0].symbol == "zebra"
    assert chunks[1].symbol == "alpha"
    assert chunks[2].symbol == "beta"

    # Verify ordering
    for i in range(len(chunks) - 1):
        assert chunks[i].start_line < chunks[i + 1].start_line


def test_tree_sitter_malformed_code():
    """Test tree-sitter handles malformed code gracefully."""
    chunker = TreeSitterChunker()
    content = """def broken(
    # Missing closing paren and colon
    return 42

def valid():
    return 1
"""

    # Should not crash, may return partial results
    chunks = chunker.chunk_file(content, Path("broken.py"), "py")
    # Tree-sitter is resilient and may still extract some chunks
    assert isinstance(chunks, list)


def test_tree_sitter_java_functions():
    """Test tree-sitter extracts Java classes and methods."""
    chunker = TreeSitterChunker()
    content = """public class Calculator {
    public Calculator() {
        // Constructor
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int multiply(int a, int b) {
        return a * b;
    }
}

interface MathOperations {
    int compute(int a, int b);
}
"""

    chunks = chunker.chunk_file(content, Path("Calculator.java"), "java")

    # Should extract class, interface, constructor, and methods
    assert len(chunks) >= 4

    # Check for class (may include constructor with same name)
    class_chunks = [c for c in chunks if c.symbol == "Calculator"]
    assert len(class_chunks) >= 1
    # Find the class definition (largest chunk)
    class_def = max(class_chunks, key=lambda c: c.end_line - c.start_line)
    assert "class Calculator" in class_def.content

    # Check for interface
    interface_chunks = [c for c in chunks if c.symbol == "MathOperations"]
    assert len(interface_chunks) == 1

    # Check for methods
    method_symbols = {c.symbol for c in chunks}
    assert "add" in method_symbols
    assert "multiply" in method_symbols


def test_tree_sitter_c_functions():
    """Test tree-sitter extracts C functions and structs."""
    chunker = TreeSitterChunker()
    content = """#include <stdio.h>

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

void print_point(struct Point p) {
    printf("Point(%d, %d)\\n", p.x, p.y);
}
"""

    chunks = chunker.chunk_file(content, Path("math.c"), "c")

    # Should extract struct and functions
    assert len(chunks) >= 3

    # Check for struct (may appear multiple times if used in function signatures)
    struct_chunks = [c for c in chunks if c.symbol == "Point"]
    assert len(struct_chunks) >= 1
    # Find the struct definition
    struct_def = [c for c in struct_chunks if "struct Point {" in c.content]
    assert len(struct_def) >= 1

    # Check for functions
    function_symbols = {c.symbol for c in chunks}
    assert "add" in function_symbols
    assert "multiply" in function_symbols
    assert "print_point" in function_symbols


def test_tree_sitter_cpp_classes():
    """Test tree-sitter extracts C++ classes and functions."""
    chunker = TreeSitterChunker()
    content = """#include <iostream>

class Calculator {
public:
    int result;

    Calculator() : result(0) {}

    int add(int a, int b) {
        return a + b;
    }
};

struct Point {
    int x, y;
};

int multiply(int a, int b) {
    return a * b;
}
"""

    chunks = chunker.chunk_file(content, Path("calc.cpp"), "cpp")

    # Should extract class, struct, and functions
    assert len(chunks) >= 3

    # Check for class (may include constructor with same name)
    class_chunks = [c for c in chunks if c.symbol == "Calculator"]
    assert len(class_chunks) >= 1
    # Find the class definition (largest chunk)
    class_def = max(class_chunks, key=lambda c: c.end_line - c.start_line)
    assert "class Calculator" in class_def.content

    # Check for struct
    struct_chunks = [c for c in chunks if c.symbol == "Point"]
    assert len(struct_chunks) >= 1

    # Check for function
    function_symbols = {c.symbol for c in chunks}
    assert "multiply" in function_symbols


def test_tree_sitter_csharp_classes():
    """Test tree-sitter extracts C# classes and methods."""
    chunker = TreeSitterChunker()
    content = """using System;

namespace MathLib
{
    public class Calculator
    {
        public Calculator()
        {
            // Constructor
        }

        public int Add(int a, int b)
        {
            return a + b;
        }

        public int Multiply(int a, int b)
        {
            return a * b;
        }
    }

    public interface IMathOperations
    {
        int Compute(int a, int b);
    }
}
"""

    chunks = chunker.chunk_file(content, Path("Calculator.cs"), "cs")

    # Should extract class, interface, constructor, and methods
    assert len(chunks) >= 4

    # Check for class (may include constructor with same name)
    class_chunks = [c for c in chunks if c.symbol == "Calculator"]
    assert len(class_chunks) >= 1
    # Find the class definition (largest chunk)
    class_def = max(class_chunks, key=lambda c: c.end_line - c.start_line)
    assert "class Calculator" in class_def.content

    # Check for interface
    interface_chunks = [c for c in chunks if c.symbol == "IMathOperations"]
    assert len(interface_chunks) == 1

    # Check for methods
    method_symbols = {c.symbol for c in chunks}
    assert "Add" in method_symbols
    assert "Multiply" in method_symbols


def test_tree_sitter_ruby_methods():
    """Test tree-sitter extracts Ruby classes and methods."""
    chunker = TreeSitterChunker()
    content = """class Calculator
  def initialize
    @result = 0
  end

  def add(a, b)
    a + b
  end

  def self.multiply(a, b)
    a * b
  end
end

module MathHelpers
  def square(x)
    x * x
  end
end
"""

    chunks = chunker.chunk_file(content, Path("calculator.rb"), "rb")

    # Should extract class, module, and methods
    assert len(chunks) >= 4

    # Check for class
    class_chunks = [c for c in chunks if c.symbol == "Calculator"]
    assert len(class_chunks) == 1
    assert "class Calculator" in class_chunks[0].content

    # Check for module
    module_chunks = [c for c in chunks if c.symbol == "MathHelpers"]
    assert len(module_chunks) == 1

    # Check for methods
    method_symbols = {c.symbol for c in chunks}
    assert "initialize" in method_symbols or "add" in method_symbols
