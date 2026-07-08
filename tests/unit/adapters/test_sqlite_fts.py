import pytest
import sqlite3
from pathlib import Path
from ember.adapters.fts.sqlite_fts import SQLiteFTS


def test_sqlite_fts_escape_query():
    """Test that FTS5 query strings are escaped correctly."""
    adapter = SQLiteFTS(Path(":memory:"))
    
    # Simple query
    assert adapter._escape_query("hello") == '"hello"'
    
    # Query with special characters
    assert adapter._escape_query("*") == '"*"'
    assert adapter._escape_query(".") == '"."'
    assert adapter._escape_query("-") == '"-"'
    assert adapter._escape_query("self.foo") == '"self.foo"'
    assert adapter._escape_query("my-special-func") == '"my-special-func"'
    
    # Query containing double quotes
    assert adapter._escape_query('foo"bar') == '"foo""bar"'


def test_sqlite_fts_query_empty():
    """Test that empty queries return empty lists without querying."""
    # We pass a non-existent path to verify that it returns [] without opening DB/connection
    adapter = SQLiteFTS(Path("/nonexistent/db.db"))
    
    assert adapter.query("") == []
    assert adapter.query("   ") == []
    assert adapter.query("\n\t") == []


def test_sqlite_fts_functional_special_chars(tmp_path: Path):
    """Test that SQLiteFTS query succeeds with special characters in database."""
    db_path = tmp_path / "test.db"
    
    # Initialize DB with FTS5 schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, chunk_id TEXT, path TEXT);")
    cursor.execute("CREATE VIRTUAL TABLE chunk_text USING fts5(content, path, symbol, lang);")
    
    # Insert test data
    cursor.execute("INSERT INTO chunks (id, chunk_id, path) VALUES (1, 'chunk_1', 'math.py');")
    cursor.execute("INSERT INTO chunk_text (rowid, content, path, symbol, lang) VALUES (1, 'def my-special-func(a, b): return a + b', 'math.py', 'my-special-func', 'python');")
    
    cursor.execute("INSERT INTO chunks (id, chunk_id, path) VALUES (2, 'chunk_2', 'utils.py');")
    cursor.execute("INSERT INTO chunk_text (rowid, content, path, symbol, lang) VALUES (2, 'self.foo = 42', 'utils.py', 'foo', 'python');")
    
    conn.commit()
    conn.close()
    
    adapter = SQLiteFTS(db_path)
    
    # Querying special character strings should succeed and return expected chunk
    results_hyphen = adapter.query("my-special-func")
    assert len(results_hyphen) == 1
    assert results_hyphen[0][0] == "chunk_1"
    
    results_dot = adapter.query("self.foo")
    assert len(results_dot) == 1
    assert results_dot[0][0] == "chunk_2"
    
    # Querying wildcards and single special characters should not crash
    assert isinstance(adapter.query("*"), list)
    assert isinstance(adapter.query("-"), list)
    assert isinstance(adapter.query("."), list)
    
    adapter.close()
