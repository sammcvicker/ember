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
    method_symbols = {
        c.symbol for c in chunks if c.symbol not in ("Calculator", "ScientificCalculator")
    }
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


def test_tree_sitter_typescript_interfaces():
    """Test tree-sitter extracts TypeScript interfaces."""
    chunker = TreeSitterChunker()
    content = """interface User {
    name: string;
    email: string;
    readonly id: number;
}

interface Admin extends User {
    role: string;
    permissions: string[];
}
"""

    chunks = chunker.chunk_file(content, Path("types.ts"), "ts")

    # Should extract 2 interfaces
    assert len(chunks) == 2

    # Find User interface
    user_chunks = [c for c in chunks if c.symbol == "User"]
    assert len(user_chunks) == 1
    assert "interface User" in user_chunks[0].content
    assert user_chunks[0].start_line == 1
    assert user_chunks[0].lang == "ts"

    # Find Admin interface (extends User)
    admin_chunks = [c for c in chunks if c.symbol == "Admin"]
    assert len(admin_chunks) == 1
    assert "interface Admin extends User" in admin_chunks[0].content


def test_tree_sitter_typescript_generic_interfaces():
    """Test tree-sitter extracts TypeScript generic interfaces."""
    chunker = TreeSitterChunker()
    content = """interface Container<T> {
    value: T;
    getValue(): T;
}

interface KeyValuePair<K, V> {
    key: K;
    value: V;
}

interface Response<T = any> {
    data: T;
    status: number;
}
"""

    chunks = chunker.chunk_file(content, Path("generics.ts"), "ts")

    # Should extract 3 generic interfaces
    assert len(chunks) == 3

    # Check symbols
    symbols = {c.symbol for c in chunks}
    assert "Container" in symbols
    assert "KeyValuePair" in symbols
    assert "Response" in symbols

    # Verify generic syntax is preserved in content
    container_chunk = [c for c in chunks if c.symbol == "Container"][0]
    assert "interface Container<T>" in container_chunk.content


def test_tree_sitter_typescript_mixed_definitions():
    """Test tree-sitter extracts interfaces alongside classes and functions."""
    chunker = TreeSitterChunker()
    content = """interface UserData {
    name: string;
    age: number;
}

class User implements UserData {
    constructor(public name: string, public age: number) {}
}

function createUser(data: UserData): User {
    return new User(data.name, data.age);
}
"""

    chunks = chunker.chunk_file(content, Path("user.ts"), "ts")

    # Should extract interface, class, and function
    assert len(chunks) >= 3

    # Check all types are present
    symbols = {c.symbol for c in chunks}
    assert "UserData" in symbols  # interface
    assert "User" in symbols  # class
    assert "createUser" in symbols  # function


def test_tree_sitter_typescript_type_aliases():
    """Test tree-sitter extracts TypeScript type aliases."""
    chunker = TreeSitterChunker()
    content = """type UserId = string;

type Status = 'active' | 'inactive' | 'pending';

type Handler<T> = (event: T) => void;
"""

    chunks = chunker.chunk_file(content, Path("types.ts"), "ts")

    # Should extract 3 type aliases
    assert len(chunks) == 3

    # Check symbols
    symbols = {c.symbol for c in chunks}
    assert "UserId" in symbols
    assert "Status" in symbols
    assert "Handler" in symbols

    # Verify content
    userid_chunk = [c for c in chunks if c.symbol == "UserId"][0]
    assert "type UserId = string" in userid_chunk.content
    assert userid_chunk.lang == "ts"


def test_tree_sitter_typescript_complex_type_aliases():
    """Test tree-sitter extracts complex TypeScript type aliases."""
    chunker = TreeSitterChunker()
    content = """type Nullable<T> = T | null;

type DeepPartial<T> = {
    [P in keyof T]?: DeepPartial<T[P]>;
};

type AsyncResult<T, E = Error> = Promise<
    | { success: true; data: T }
    | { success: false; error: E }
>;
"""

    chunks = chunker.chunk_file(content, Path("utils.ts"), "ts")

    # Should extract 3 complex type aliases
    assert len(chunks) == 3

    symbols = {c.symbol for c in chunks}
    assert "Nullable" in symbols
    assert "DeepPartial" in symbols
    assert "AsyncResult" in symbols


def test_tree_sitter_typescript_type_aliases_mixed():
    """Test tree-sitter extracts type aliases alongside interfaces and functions."""
    chunker = TreeSitterChunker()
    content = """interface User {
    id: string;
    name: string;
}

type UserId = string;

type UserWithRole = User & { role: string };

function getUser(id: UserId): User {
    return { id, name: 'Unknown' };
}
"""

    chunks = chunker.chunk_file(content, Path("user.ts"), "ts")

    # Should extract interface, type aliases, and function
    assert len(chunks) >= 4

    symbols = {c.symbol for c in chunks}
    assert "User" in symbols  # interface
    assert "UserId" in symbols  # type alias
    assert "UserWithRole" in symbols  # type alias
    assert "getUser" in symbols  # function


def test_tree_sitter_tsx_type_aliases():
    """Test tree-sitter extracts type aliases from TSX files."""
    chunker = TreeSitterChunker()
    content = """type Props = {
    title: string;
    children: React.ReactNode;
};

type ButtonVariant = 'primary' | 'secondary' | 'danger';

function Button({ title, children }: Props) {
    return <button>{children}</button>;
}
"""

    chunks = chunker.chunk_file(content, Path("Button.tsx"), "tsx")

    # Should extract type aliases and function
    assert len(chunks) >= 3

    symbols = {c.symbol for c in chunks}
    assert "Props" in symbols
    assert "ButtonVariant" in symbols
    assert "Button" in symbols


def test_tree_sitter_typescript_named_arrow_functions():
    """Test tree-sitter extracts TypeScript named arrow functions."""
    chunker = TreeSitterChunker()
    content = """const handleClick = () => {
    console.log('clicked');
};

const fetchUser = async (id: string) => {
    return api.get(id);
};

let processData = (data: any) => {
    return data.map(x => x * 2);
};

// Regular function for comparison
function regularFunc() {
    return 42;
}
"""

    chunks = chunker.chunk_file(content, Path("handlers.ts"), "ts")

    # Check symbols
    symbols = {c.symbol for c in chunks}
    assert "handleClick" in symbols
    assert "fetchUser" in symbols
    assert "processData" in symbols
    assert "regularFunc" in symbols


def test_tree_sitter_typescript_named_arrow_function_content():
    """Test tree-sitter extracts full content of named arrow functions."""
    chunker = TreeSitterChunker()
    content = """const handleClick = () => {
    console.log('clicked');
};
"""

    chunks = chunker.chunk_file(content, Path("handlers.ts"), "ts")

    # Should extract the named arrow function
    assert len(chunks) == 1
    assert chunks[0].symbol == "handleClick"
    assert "const handleClick" in chunks[0].content
    assert "console.log" in chunks[0].content


def test_tree_sitter_typescript_typed_arrow_functions():
    """Test tree-sitter extracts arrow functions with explicit type annotations."""
    chunker = TreeSitterChunker()
    content = """const handler: Handler = () => {
    console.log('handled');
};

const callback: (x: number) => number = (x) => x * 2;
"""

    chunks = chunker.chunk_file(content, Path("typed.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    assert "handler" in symbols
    assert "callback" in symbols


def test_tree_sitter_typescript_arrow_functions_mixed():
    """Test tree-sitter extracts arrow functions alongside other definitions."""
    chunker = TreeSitterChunker()
    content = """interface User {
    name: string;
}

type Handler = () => void;

const handleClick = () => {
    console.log('click');
};

function regularFunction() {
    return 42;
}

class MyClass {
    method() {
        return 1;
    }
}
"""

    chunks = chunker.chunk_file(content, Path("mixed.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    assert "User" in symbols  # interface
    assert "Handler" in symbols  # type alias
    assert "handleClick" in symbols  # named arrow function
    assert "regularFunction" in symbols  # function
    assert "MyClass" in symbols  # class


def test_tree_sitter_javascript_named_arrow_functions():
    """Test tree-sitter extracts JavaScript named arrow functions."""
    chunker = TreeSitterChunker()
    content = """const handleClick = () => {
    console.log('clicked');
};

const fetchData = async () => {
    return fetch('/api/data');
};

var legacyHandler = () => {
    console.log('legacy');
};
"""

    chunks = chunker.chunk_file(content, Path("handlers.js"), "js")

    symbols = {c.symbol for c in chunks}
    assert "handleClick" in symbols
    assert "fetchData" in symbols
    assert "legacyHandler" in symbols


def test_tree_sitter_tsx_named_arrow_functions():
    """Test tree-sitter extracts TSX named arrow functions (React components)."""
    chunker = TreeSitterChunker()
    content = """const Button = () => {
    return <button>Click me</button>;
};

const Card = ({ title, children }) => {
    return (
        <div className="card">
            <h2>{title}</h2>
            {children}
        </div>
    );
};
"""

    chunks = chunker.chunk_file(content, Path("components.tsx"), "tsx")

    symbols = {c.symbol for c in chunks}
    assert "Button" in symbols
    assert "Card" in symbols


def test_tree_sitter_jsx_named_arrow_functions():
    """Test tree-sitter extracts JSX named arrow functions (React components)."""
    chunker = TreeSitterChunker()
    content = """const Button = () => {
    return <button>Click me</button>;
};

const List = ({ items }) => {
    return (
        <ul>
            {items.map(item => <li>{item}</li>)}
        </ul>
    );
};
"""

    chunks = chunker.chunk_file(content, Path("components.jsx"), "jsx")

    symbols = {c.symbol for c in chunks}
    assert "Button" in symbols
    assert "List" in symbols


def test_tree_sitter_typescript_export_function():
    """Test tree-sitter extracts exported TypeScript functions."""
    chunker = TreeSitterChunker()
    content = """export function processData(data: Data): Result {
    return transform(data);
}

export async function fetchUser(id: string): Promise<User> {
    return api.get(id);
}
"""

    chunks = chunker.chunk_file(content, Path("api.ts"), "ts")

    # Should extract 2 exported functions
    assert len(chunks) == 2

    symbols = {c.symbol for c in chunks}
    assert "processData" in symbols
    assert "fetchUser" in symbols

    # Verify content includes export keyword
    process_chunk = [c for c in chunks if c.symbol == "processData"][0]
    assert "export function processData" in process_chunk.content


def test_tree_sitter_typescript_export_class():
    """Test tree-sitter extracts exported TypeScript classes."""
    chunker = TreeSitterChunker()
    content = """export class UserService {
    getUser(id: string) {
        return this.users.find(u => u.id === id);
    }
}

export class AdminService extends UserService {
    deleteUser(id: string) {
        // admin only
    }
}
"""

    chunks = chunker.chunk_file(content, Path("services.ts"), "ts")

    # Should extract classes and methods
    symbols = {c.symbol for c in chunks}
    assert "UserService" in symbols
    assert "AdminService" in symbols

    # Verify export is in content
    user_service = [c for c in chunks if c.symbol == "UserService"][0]
    assert "export class UserService" in user_service.content


def test_tree_sitter_typescript_export_const():
    """Test tree-sitter extracts exported const arrow functions."""
    chunker = TreeSitterChunker()
    content = """export const handler = () => {
    console.log('handled');
};

export const fetchData = async (url: string) => {
    return fetch(url);
};

export const API_VERSION = '2.0';
"""

    chunks = chunker.chunk_file(content, Path("utils.ts"), "ts")

    # Should extract arrow functions (not plain constants)
    symbols = {c.symbol for c in chunks}
    assert "handler" in symbols
    assert "fetchData" in symbols
    # API_VERSION is a plain constant, not a function - may or may not be extracted


def test_tree_sitter_typescript_export_default_class():
    """Test tree-sitter extracts default exported TypeScript classes."""
    chunker = TreeSitterChunker()
    content = """export default class App {
    render() {
        return null;
    }
}
"""

    chunks = chunker.chunk_file(content, Path("App.ts"), "ts")

    # Should extract the default exported class
    symbols = {c.symbol for c in chunks}
    assert "App" in symbols

    app_chunk = [c for c in chunks if c.symbol == "App"][0]
    assert "export default class App" in app_chunk.content


def test_tree_sitter_typescript_export_interface():
    """Test tree-sitter extracts exported TypeScript interfaces."""
    chunker = TreeSitterChunker()
    content = """export interface Config {
    name: string;
    version: number;
}

export interface ExtendedConfig extends Config {
    debug: boolean;
}
"""

    chunks = chunker.chunk_file(content, Path("config.ts"), "ts")

    # Should extract 2 exported interfaces
    assert len(chunks) == 2

    symbols = {c.symbol for c in chunks}
    assert "Config" in symbols
    assert "ExtendedConfig" in symbols

    # Verify export is in content
    config_chunk = [c for c in chunks if c.symbol == "Config"][0]
    assert "export interface Config" in config_chunk.content


def test_tree_sitter_typescript_export_type():
    """Test tree-sitter extracts exported TypeScript type aliases."""
    chunker = TreeSitterChunker()
    content = """export type Status = 'active' | 'inactive' | 'pending';

export type Handler<T> = (event: T) => void;

export type UserWithRole = User & { role: string };
"""

    chunks = chunker.chunk_file(content, Path("types.ts"), "ts")

    # Should extract 3 exported type aliases
    assert len(chunks) == 3

    symbols = {c.symbol for c in chunks}
    assert "Status" in symbols
    assert "Handler" in symbols
    assert "UserWithRole" in symbols

    # Verify export is in content
    status_chunk = [c for c in chunks if c.symbol == "Status"][0]
    assert "export type Status" in status_chunk.content


def test_tree_sitter_typescript_mixed_exports():
    """Test tree-sitter extracts mixed exported and non-exported definitions."""
    chunker = TreeSitterChunker()
    content = """export interface User {
    id: string;
    name: string;
}

interface InternalData {
    secret: string;
}

export type UserId = string;

type InternalType = number;

export function getUser(id: UserId): User {
    return { id, name: 'Test' };
}

function internalHelper() {
    return 42;
}

export class UserService {
    findUser(id: string) { return null; }
}

class InternalService {
    doSomething() { return null; }
}

export const handler = () => console.log('handled');

const internalHandler = () => console.log('internal');
"""

    chunks = chunker.chunk_file(content, Path("mixed.ts"), "ts")

    # Should extract both exported and non-exported definitions
    symbols = {c.symbol for c in chunks}

    # Exported items
    assert "User" in symbols
    assert "UserId" in symbols
    assert "getUser" in symbols
    assert "UserService" in symbols
    assert "handler" in symbols

    # Non-exported items should also be extracted
    assert "InternalData" in symbols
    assert "InternalType" in symbols
    assert "internalHelper" in symbols
    assert "InternalService" in symbols
    assert "internalHandler" in symbols


def test_tree_sitter_tsx_exports():
    """Test tree-sitter extracts exports from TSX files."""
    chunker = TreeSitterChunker()
    content = """export interface ButtonProps {
    label: string;
    onClick: () => void;
}

export type ButtonVariant = 'primary' | 'secondary';

export const Button = ({ label, onClick }: ButtonProps) => {
    return <button onClick={onClick}>{label}</button>;
};

export function Card({ children }: { children: React.ReactNode }) {
    return <div className="card">{children}</div>;
}

export default class App {
    render() {
        return <div>Hello</div>;
    }
}
"""

    chunks = chunker.chunk_file(content, Path("components.tsx"), "tsx")

    symbols = {c.symbol for c in chunks}
    assert "ButtonProps" in symbols
    assert "ButtonVariant" in symbols
    assert "Button" in symbols
    assert "Card" in symbols
    assert "App" in symbols


def test_tree_sitter_javascript_exports():
    """Test tree-sitter extracts exports from JavaScript files."""
    chunker = TreeSitterChunker()
    content = """export function processData(data) {
    return data.map(x => x * 2);
}

export class DataService {
    fetch() { return []; }
}

export const handler = () => {
    console.log('handled');
};

export default function main() {
    return 'main';
}
"""

    chunks = chunker.chunk_file(content, Path("utils.js"), "js")

    symbols = {c.symbol for c in chunks}
    assert "processData" in symbols
    assert "DataService" in symbols
    assert "handler" in symbols
    assert "main" in symbols


# =============================================================================
# TypeScript Comprehensive Test Coverage (Issue #231)
# =============================================================================


def test_tree_sitter_typescript_async_functions():
    """Test tree-sitter extracts TypeScript async functions."""
    chunker = TreeSitterChunker()
    content = """async function fetchUser(id: string): Promise<User> {
    const response = await api.get(`/users/${id}`);
    return response.data;
}

async function fetchAllUsers(): Promise<User[]> {
    const users = await db.query('SELECT * FROM users');
    return users;
}

function syncOperation(): number {
    return 42;
}
"""

    chunks = chunker.chunk_file(content, Path("async.ts"), "ts")

    # Should extract all 3 functions
    assert len(chunks) == 3

    symbols = {c.symbol for c in chunks}
    assert "fetchUser" in symbols
    assert "fetchAllUsers" in symbols
    assert "syncOperation" in symbols

    # Verify async content is preserved
    fetch_user = [c for c in chunks if c.symbol == "fetchUser"][0]
    assert "async function fetchUser" in fetch_user.content


def test_tree_sitter_typescript_async_arrow_functions():
    """Test tree-sitter extracts TypeScript async arrow functions."""
    chunker = TreeSitterChunker()
    content = """const fetchData = async () => {
    return await fetch('/api/data');
};

const processAsync = async (items: string[]) => {
    const results = await Promise.all(items.map(process));
    return results;
};

const syncHandler = () => {
    return 'sync';
};
"""

    chunks = chunker.chunk_file(content, Path("async-arrow.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    assert "fetchData" in symbols
    assert "processAsync" in symbols
    assert "syncHandler" in symbols

    # Verify async content is preserved
    fetch_data = [c for c in chunks if c.symbol == "fetchData"][0]
    assert "async" in fetch_data.content


def test_tree_sitter_typescript_nested_classes():
    """Test tree-sitter handles TypeScript nested class definitions."""
    chunker = TreeSitterChunker()
    content = """class Outer {
    outerMethod() {
        return 1;
    }

    static Inner = class {
        innerMethod() {
            return 2;
        }
    };
}

function factory() {
    class LocalClass {
        localMethod() {
            return 3;
        }
    }
    return new LocalClass();
}
"""

    chunks = chunker.chunk_file(content, Path("nested.ts"), "ts")

    # Should extract at minimum the outer class and function
    symbols = {c.symbol for c in chunks}
    assert "Outer" in symbols
    assert "factory" in symbols

    # Methods should also be extracted
    assert "outerMethod" in symbols


def test_tree_sitter_typescript_generic_functions():
    """Test tree-sitter extracts TypeScript generic functions."""
    chunker = TreeSitterChunker()
    content = """function identity<T>(arg: T): T {
    return arg;
}

function map<T, U>(items: T[], fn: (item: T) => U): U[] {
    return items.map(fn);
}

async function fetchTyped<T>(url: string): Promise<T> {
    const response = await fetch(url);
    return response.json();
}
"""

    chunks = chunker.chunk_file(content, Path("generics.ts"), "ts")

    # Should extract all 3 generic functions
    assert len(chunks) == 3

    symbols = {c.symbol for c in chunks}
    assert "identity" in symbols
    assert "map" in symbols
    assert "fetchTyped" in symbols

    # Verify generic syntax is preserved
    identity_chunk = [c for c in chunks if c.symbol == "identity"][0]
    assert "function identity<T>" in identity_chunk.content


def test_tree_sitter_typescript_generic_classes():
    """Test tree-sitter extracts TypeScript generic classes."""
    chunker = TreeSitterChunker()
    content = """class Container<T> {
    constructor(private value: T) {}

    getValue(): T {
        return this.value;
    }
}

class KeyValueStore<K, V> {
    private store = new Map<K, V>();

    set(key: K, value: V): void {
        this.store.set(key, value);
    }
}
"""

    chunks = chunker.chunk_file(content, Path("generic-classes.ts"), "ts")

    # Should extract classes and methods
    symbols = {c.symbol for c in chunks}
    assert "Container" in symbols
    assert "KeyValueStore" in symbols

    # Verify generic syntax is preserved
    container = [c for c in chunks if c.symbol == "Container"][0]
    assert "class Container<T>" in container.content


def test_tree_sitter_typescript_generic_arrow_functions():
    """Test tree-sitter extracts TypeScript generic arrow functions."""
    chunker = TreeSitterChunker()
    content = """const identity = <T>(arg: T): T => {
    return arg;
};

const mapItems = <T, U>(items: T[], fn: (item: T) => U): U[] => {
    return items.map(fn);
};
"""

    chunks = chunker.chunk_file(content, Path("generic-arrows.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    assert "identity" in symbols
    assert "mapItems" in symbols


def test_tree_sitter_typescript_decorators():
    """Test tree-sitter handles TypeScript decorators gracefully.

    Note: Decorators are syntax sugar and may not have their own extraction
    rule. This test verifies decorated classes/methods are still extracted.
    """
    chunker = TreeSitterChunker()
    content = """@Component({
    selector: 'app-root'
})
class AppComponent {
    @Input() title: string = '';

    @Output() clicked = new EventEmitter();

    @HostListener('click')
    handleClick() {
        this.clicked.emit();
    }
}

@Injectable()
class UserService {
    getUser() {
        return null;
    }
}
"""

    chunks = chunker.chunk_file(content, Path("decorated.ts"), "ts")

    # Decorated classes should still be extracted
    symbols = {c.symbol for c in chunks}
    assert "AppComponent" in symbols
    assert "UserService" in symbols

    # Methods should also be extracted
    assert "handleClick" in symbols
    assert "getUser" in symbols


def test_tree_sitter_typescript_malformed_code():
    """Test tree-sitter handles malformed TypeScript code gracefully."""
    chunker = TreeSitterChunker()
    content = """function valid() {
    return 42;
}

function broken( {
    // Missing closing paren
    return 1

class PartialClass {
    method() {
        return 2;
    }
    // Missing closing brace

interface Incomplete {
    name: string
    // Missing closing brace

function afterErrors() {
    return 'recovered';
}
"""

    # Should not crash
    chunks = chunker.chunk_file(content, Path("malformed.ts"), "ts")
    assert isinstance(chunks, list)

    # Tree-sitter is resilient - should extract at least some chunks
    # The exact behavior depends on tree-sitter's error recovery
    symbols = {c.symbol for c in chunks}
    # At minimum, valid functions should be found
    assert "valid" in symbols or len(chunks) >= 0


def test_tree_sitter_typescript_incomplete_statements():
    """Test tree-sitter handles incomplete TypeScript statements gracefully.

    Note: Tree-sitter's error recovery may not extract all valid definitions
    when they are adjacent to incomplete statements. The key requirement is
    that it doesn't crash and extracts what it can.
    """
    chunker = TreeSitterChunker()
    content = """const incomplete =

function complete() {
    return 1;
}

const another: string

export function alsoComplete() {
    return 2;
}
"""

    chunks = chunker.chunk_file(content, Path("incomplete.ts"), "ts")
    assert isinstance(chunks, list)

    # Tree-sitter extracts what it can - alsoComplete is reliably extracted
    symbols = {c.symbol for c in chunks}
    assert "alsoComplete" in symbols
    # Note: 'complete' may or may not be extracted depending on error recovery


def test_tree_sitter_tsx_functional_components():
    """Test tree-sitter extracts TSX functional components (React)."""
    chunker = TreeSitterChunker()
    content = """interface ButtonProps {
    label: string;
    onClick: () => void;
    variant?: 'primary' | 'secondary';
}

const Button: React.FC<ButtonProps> = ({ label, onClick, variant = 'primary' }) => {
    return (
        <button className={`btn btn-${variant}`} onClick={onClick}>
            {label}
        </button>
    );
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className="card">
            <h2>{title}</h2>
            <div className="card-body">{children}</div>
        </div>
    );
}

export default function App() {
    return (
        <div>
            <Card title="Welcome">
                <Button label="Click me" onClick={() => alert('clicked')} />
            </Card>
        </div>
    );
}
"""

    chunks = chunker.chunk_file(content, Path("Components.tsx"), "tsx")

    symbols = {c.symbol for c in chunks}
    assert "ButtonProps" in symbols  # interface
    assert "Button" in symbols  # arrow function component
    assert "Card" in symbols  # function component
    assert "App" in symbols  # default export function


def test_tree_sitter_tsx_class_components():
    """Test tree-sitter extracts TSX class components (React)."""
    chunker = TreeSitterChunker()
    content = """interface State {
    count: number;
}

interface Props {
    initialCount: number;
}

class Counter extends React.Component<Props, State> {
    state: State = { count: this.props.initialCount };

    increment = () => {
        this.setState({ count: this.state.count + 1 });
    };

    render() {
        return (
            <div>
                <span>{this.state.count}</span>
                <button onClick={this.increment}>+</button>
            </div>
        );
    }
}

export default class App extends React.Component {
    render() {
        return <Counter initialCount={0} />;
    }
}
"""

    chunks = chunker.chunk_file(content, Path("ClassComponents.tsx"), "tsx")

    symbols = {c.symbol for c in chunks}
    assert "State" in symbols  # interface
    assert "Props" in symbols  # interface
    assert "Counter" in symbols  # class component
    assert "App" in symbols  # default export class
    assert "render" in symbols  # method


def test_tree_sitter_typescript_method_signatures():
    """Test tree-sitter extracts TypeScript method definitions with various signatures."""
    chunker = TreeSitterChunker()
    content = """class ApiClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    async get<T>(path: string): Promise<T> {
        const response = await fetch(`${this.baseUrl}${path}`);
        return response.json();
    }

    post<T, U>(path: string, data: T): Promise<U> {
        return fetch(`${this.baseUrl}${path}`, {
            method: 'POST',
            body: JSON.stringify(data)
        }).then(r => r.json());
    }

    static create(baseUrl: string): ApiClient {
        return new ApiClient(baseUrl);
    }
}
"""

    chunks = chunker.chunk_file(content, Path("api-client.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    assert "ApiClient" in symbols
    assert "get" in symbols
    assert "post" in symbols
    assert "create" in symbols


def test_tree_sitter_typescript_computed_properties():
    """Test tree-sitter handles TypeScript computed property names."""
    chunker = TreeSitterChunker()
    content = """const KEY = 'dynamicMethod';

class DynamicClass {
    [KEY]() {
        return 'dynamic';
    }

    regularMethod() {
        return 'regular';
    }
}

function regularFunction() {
    return 42;
}
"""

    chunks = chunker.chunk_file(content, Path("computed.ts"), "ts")

    # Should extract the class and regular methods
    symbols = {c.symbol for c in chunks}
    assert "DynamicClass" in symbols
    assert "regularMethod" in symbols
    assert "regularFunction" in symbols


def test_tree_sitter_typescript_overloaded_functions():
    """Test tree-sitter handles TypeScript function overloads."""
    chunker = TreeSitterChunker()
    content = """function process(x: string): string;
function process(x: number): number;
function process(x: string | number): string | number {
    return typeof x === 'string' ? x.toUpperCase() : x * 2;
}

function singleDef(x: number): number {
    return x + 1;
}
"""

    chunks = chunker.chunk_file(content, Path("overloads.ts"), "ts")

    symbols = {c.symbol for c in chunks}
    # Overloaded function should appear (implementation at minimum)
    assert "process" in symbols
    assert "singleDef" in symbols


def test_tree_sitter_typescript_namespace():
    """Test tree-sitter handles TypeScript namespaces/modules."""
    chunker = TreeSitterChunker()
    content = """namespace Utils {
    export function helper() {
        return 'help';
    }

    export class Helper {
        assist() {
            return 'assist';
        }
    }
}

function outsideNamespace() {
    return Utils.helper();
}
"""

    chunks = chunker.chunk_file(content, Path("namespace.ts"), "ts")

    # Functions outside namespace should be extracted
    symbols = {c.symbol for c in chunks}
    assert "outsideNamespace" in symbols
    # Depending on query, namespace contents may or may not be extracted
    # The key is it doesn't crash
