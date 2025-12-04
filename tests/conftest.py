"""Pytest configuration and shared fixtures."""

import gc
import subprocess
import tempfile
from pathlib import Path

import pytest

from ember.adapters.sqlite.schema import init_database
from ember.domain.entities import Chunk


@pytest.fixture(autouse=True)
def cleanup_database_connections():
    """Automatically clean up database connections after each test.

    This fixture ensures that any unclosed SQLite database connections
    are properly garbage collected after each test, preventing
    ResourceWarning messages about unclosed database connections.

    The fixture is autouse=True so it runs automatically for every test.
    It runs gc.collect() twice to ensure finalizers are called.
    """
    yield
    # Force garbage collection twice to ensure finalizers run
    # First pass marks objects for collection, second pass runs finalizers
    gc.collect()
    gc.collect()


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for tests.

    Yields:
        Path to temporary directory (cleaned up after test).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunk() -> Chunk:
    """Create a sample chunk for testing.

    Returns:
        A Chunk instance with test data.
    """
    return Chunk(
        id="test_chunk_123",
        project_id="test_project",
        path=Path("src/example.py"),
        lang="py",
        symbol="test_function",
        start_line=10,
        end_line=20,
        content='def test_function():\n    return "hello"',
        content_hash=Chunk.compute_content_hash('def test_function():\n    return "hello"'),
        file_hash="abc123",
        tree_sha="def456",
        rev="HEAD",
    )


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    """Create multiple sample chunks for testing.

    Returns:
        List of Chunk instances.
    """
    chunks = []
    for i in range(5):
        # Start lines at 1 (1-indexed) to satisfy validation
        start_line = (i * 10) + 1
        end_line = start_line + 10
        chunk = Chunk(
            id=f"chunk_{i}",
            project_id="test_project",
            path=Path(f"src/file_{i}.py"),
            lang="py",
            symbol=f"function_{i}",
            start_line=start_line,
            end_line=end_line,
            content=f"def function_{i}():\n    pass",
            content_hash=Chunk.compute_content_hash(f"def function_{i}():\n    pass"),
            file_hash=f"hash_{i}",
            tree_sha="tree_sha_test",
            rev="HEAD",
        )
        chunks.append(chunk)
    return chunks


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a standard git repository with test files.

    Creates a git repository with:
    - Two Python files (math.py, utils.py)
    - Proper git configuration
    - Initial commit

    Returns:
        Path to the git repository root.
    """
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )

    # Create test files
    math_file = repo_root / "math.py"
    math_file.write_text("""def add(a, b):
    '''Add two numbers.'''
    return a + b


def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
""")

    utils_file = repo_root / "utils.py"
    utils_file.write_text("""def greet(name):
    '''Greet someone.'''
    return f"Hello, {name}!"
""")

    # Commit files
    subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, timeout=5)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        timeout=5,
    )

    return repo_root


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database with schema initialized.

    Returns:
        Path to the initialized test database.

    Note:
        Database connection cleanup is handled by the autouse
        cleanup_database_connections fixture.
    """
    db = tmp_path / "test.db"
    init_database(db)
    return db


@pytest.fixture
def realistic_repo(tmp_path: Path) -> Path:
    """Create a realistic git repository with diverse files for testing.

    Creates a repository with:
    - 10+ files across multiple languages (Python, JavaScript, TypeScript, Markdown)
    - Realistic code patterns (classes, functions, docstrings, comments)
    - Nested directory structure
    - 100+ potential code chunks for testing indexing and search

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the created repository root.
    """
    repo_path = tmp_path / "realistic_repo"
    repo_path.mkdir()

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, timeout=5, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        timeout=5,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        timeout=5,
        capture_output=True,
    )

    # Create directory structure
    (repo_path / "src").mkdir()
    (repo_path / "src" / "utils").mkdir()
    (repo_path / "src" / "models").mkdir()
    (repo_path / "tests").mkdir()
    (repo_path / "docs").mkdir()

    # File 1: Main application file with multiple classes
    (repo_path / "src" / "app.py").write_text(
        '''"""Main application module for the web service.

This module provides the core application logic including request handling,
database operations, and API endpoints.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Application:
    """Main application class that coordinates service operations.

    Attributes:
        config: Application configuration dictionary
        db_connection: Database connection instance
        is_running: Boolean indicating if app is running
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the application with configuration.

        Args:
            config: Dictionary containing application settings
        """
        self.config = config
        self.db_connection = None
        self.is_running = False
        logger.info("Application initialized with config: %s", config)

    def start(self) -> None:
        """Start the application and connect to database."""
        logger.info("Starting application...")
        self._connect_database()
        self.is_running = True
        logger.info("Application started successfully")

    def stop(self) -> None:
        """Stop the application and cleanup resources."""
        logger.info("Stopping application...")
        self._disconnect_database()
        self.is_running = False
        logger.info("Application stopped")

    def _connect_database(self) -> None:
        """Establish database connection using config settings."""
        db_url = self.config.get("database_url", "sqlite:///default.db")
        logger.debug("Connecting to database: %s", db_url)
        # Database connection logic would go here
        self.db_connection = {"url": db_url, "connected": True}

    def _disconnect_database(self) -> None:
        """Close database connection and cleanup."""
        if self.db_connection:
            logger.debug("Disconnecting from database")
            self.db_connection = None

    def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming request and return response.

        Args:
            request_data: Dictionary containing request parameters

        Returns:
            Dictionary containing response data

        Raises:
            ValueError: If request data is invalid
        """
        if not self.is_running:
            raise RuntimeError("Application is not running")

        action = request_data.get("action")
        if not action:
            raise ValueError("Request must specify an action")

        logger.info("Handling request with action: %s", action)

        # Process based on action type
        if action == "query":
            return self._handle_query(request_data)
        elif action == "update":
            return self._handle_update(request_data)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

    def _handle_query(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle database query requests."""
        query = request_data.get("query", "")
        logger.debug("Executing query: %s", query)
        return {"status": "success", "results": [], "query": query}

    def _handle_update(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle database update requests."""
        data = request_data.get("data", {})
        logger.debug("Updating data: %s", data)
        return {"status": "success", "updated": True}
'''
    )

    # File 2: Utility functions
    (repo_path / "src" / "utils" / "helpers.py").write_text(
        '''"""Helper utility functions for data processing and validation.

This module provides common utility functions used across the application.
"""

import re
from typing import List, Optional, Union
from datetime import datetime


def validate_email(email: str) -> bool:
    """Validate email address format.

    Args:
        email: Email address string to validate

    Returns:
        True if email format is valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename.

    Args:
        filename: Original filename string

    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Format datetime as ISO 8601 string.

    Args:
        dt: Datetime object to format, defaults to current time

    Returns:
        ISO 8601 formatted timestamp string
    """
    if dt is None:
        dt = datetime.now()
    return dt.isoformat()


def parse_csv_line(line: str, delimiter: str = ',') -> List[str]:
    """Parse a CSV line into fields.

    Args:
        line: CSV line string to parse
        delimiter: Field delimiter character

    Returns:
        List of parsed field values
    """
    return [field.strip() for field in line.split(delimiter)]


def calculate_percentage(part: Union[int, float], total: Union[int, float]) -> float:
    """Calculate percentage value.

    Args:
        part: Part value (numerator)
        total: Total value (denominator)

    Returns:
        Percentage as float (0-100)

    Raises:
        ValueError: If total is zero
    """
    if total == 0:
        raise ValueError("Cannot calculate percentage with zero total")
    return (part / total) * 100


def truncate_string(text: str, max_length: int, suffix: str = '...') -> str:
    """Truncate string to maximum length.

    Args:
        text: String to truncate
        max_length: Maximum allowed length
        suffix: Suffix to append if truncated

    Returns:
        Truncated string with suffix if needed
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def chunk_list(items: List[any], chunk_size: int) -> List[List[any]]:
    """Split list into chunks of specified size.

    Args:
        items: List to split into chunks
        chunk_size: Size of each chunk

    Returns:
        List of chunked sublists

    Raises:
        ValueError: If chunk_size is less than 1
    """
    if chunk_size < 1:
        raise ValueError("Chunk size must be at least 1")

    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i : i + chunk_size])
    return chunks
'''
    )

    # File 3: Data models
    (repo_path / "src" / "models" / "user.py").write_text(
        '''"""User data model and related operations.

This module defines the User entity and associated data access methods.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Represents a user in the system.

    Attributes:
        id: Unique user identifier
        email: User email address
        username: User's display name
        created_at: Account creation timestamp
        is_active: Whether the account is active
        last_login: Timestamp of last login
    """

    id: int
    email: str
    username: str
    created_at: datetime
    is_active: bool = True
    last_login: Optional[datetime] = None

    def __post_init__(self):
        """Validate user data after initialization."""
        if not self.email or '@' not in self.email:
            raise ValueError(f"Invalid email address: {self.email}")
        if not self.username or len(self.username) < 3:
            raise ValueError("Username must be at least 3 characters")

    def deactivate(self) -> None:
        """Deactivate the user account."""
        self.is_active = False

    def activate(self) -> None:
        """Activate the user account."""
        self.is_active = True

    def update_last_login(self) -> None:
        """Update the last login timestamp to current time."""
        self.last_login = datetime.now()

    def to_dict(self) -> dict:
        """Convert user to dictionary representation.

        Returns:
            Dictionary with user data
        """
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create User instance from dictionary.

        Args:
            data: Dictionary containing user data

        Returns:
            New User instance
        """
        return cls(
            id=data["id"],
            email=data["email"],
            username=data["username"],
            created_at=datetime.fromisoformat(data["created_at"]),
            is_active=data.get("is_active", True),
            last_login=datetime.fromisoformat(data["last_login"]) if data.get("last_login") else None,
        )
'''
    )

    # File 4: JavaScript React component
    (repo_path / "src" / "components.jsx").write_text(
        """/**
 * React components for the user interface.
 *
 * This module provides reusable UI components for the application.
 */

import React, { useState, useEffect } from 'react';

/**
 * UserProfile component displays user information.
 *
 * @param {Object} props - Component props
 * @param {Object} props.user - User object with id, name, email
 * @param {Function} props.onUpdate - Callback when user is updated
 * @returns {JSX.Element} Rendered component
 */
export function UserProfile({ user, onUpdate }) {
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    name: user.name,
    email: user.email,
  });

  useEffect(() => {
    setFormData({ name: user.name, email: user.email });
  }, [user]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    await onUpdate(formData);
    setIsEditing(false);
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  if (isEditing) {
    return (
      <form onSubmit={handleSubmit} className="user-profile-form">
        <input
          type="text"
          name="name"
          value={formData.name}
          onChange={handleChange}
          placeholder="Name"
        />
        <input
          type="email"
          name="email"
          value={formData.email}
          onChange={handleChange}
          placeholder="Email"
        />
        <button type="submit">Save</button>
        <button type="button" onClick={() => setIsEditing(false)}>
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="user-profile">
      <h2>{user.name}</h2>
      <p>{user.email}</p>
      <button onClick={() => setIsEditing(true)}>Edit Profile</button>
    </div>
  );
}

/**
 * DataTable component for displaying tabular data.
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Array of data objects
 * @param {Array} props.columns - Column configuration
 * @returns {JSX.Element} Rendered table
 */
export function DataTable({ data, columns }) {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  const sortedData = React.useMemo(() => {
    if (!sortConfig.key) return data;

    return [...data].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];

      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [data, sortConfig]);

  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map(col => (
            <th key={col.key} onClick={() => requestSort(col.key)}>
              {col.label}
              {sortConfig.key === col.key && (
                <span>{sortConfig.direction === 'asc' ? ' ↑' : ' ↓'}</span>
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedData.map((row, idx) => (
          <tr key={idx}>
            {columns.map(col => (
              <td key={col.key}>{row[col.key]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
"""
    )

    # File 5: TypeScript API client
    (repo_path / "src" / "api-client.ts").write_text(
        """/**
 * API client for backend communication.
 *
 * Provides type-safe methods for making API requests.
 */

export interface ApiResponse<T> {
  data: T;
  status: number;
  message?: string;
}

export interface User {
  id: number;
  email: string;
  username: string;
  createdAt: string;
  isActive: boolean;
}

export interface QueryParams {
  page?: number;
  limit?: number;
  sort?: string;
  filter?: Record<string, any>;
}

/**
 * Main API client class for making HTTP requests.
 */
export class ApiClient {
  private baseUrl: string;
  private headers: Record<string, string>;

  constructor(baseUrl: string, authToken?: string) {
    this.baseUrl = baseUrl;
    this.headers = {
      'Content-Type': 'application/json',
    };

    if (authToken) {
      this.headers['Authorization'] = `Bearer ${authToken}`;
    }
  }

  /**
   * Make a GET request to the API.
   */
  async get<T>(endpoint: string, params?: QueryParams): Promise<ApiResponse<T>> {
    const url = new URL(endpoint, this.baseUrl);

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: this.headers,
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Make a POST request to the API.
   */
  async post<T>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify(data),
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Make a PUT request to the API.
   */
  async put<T>(endpoint: string, data: any): Promise<ApiResponse<T>> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'PUT',
      headers: this.headers,
      body: JSON.stringify(data),
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Make a DELETE request to the API.
   */
  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'DELETE',
      headers: this.headers,
    });

    return this.handleResponse<T>(response);
  }

  /**
   * Handle API response and extract data.
   */
  private async handleResponse<T>(response: Response): Promise<ApiResponse<T>> {
    const contentType = response.headers.get('content-type');
    const isJson = contentType?.includes('application/json');

    if (!response.ok) {
      const error = isJson ? await response.json() : { message: response.statusText };
      throw new Error(error.message || 'API request failed');
    }

    const data = isJson ? await response.json() : null;

    return {
      data,
      status: response.status,
    };
  }

  /**
   * Fetch all users with optional filtering.
   */
  async getUsers(params?: QueryParams): Promise<User[]> {
    const response = await this.get<User[]>('/users', params);
    return response.data;
  }

  /**
   * Fetch a single user by ID.
   */
  async getUser(id: number): Promise<User> {
    const response = await this.get<User>(`/users/${id}`);
    return response.data;
  }

  /**
   * Create a new user.
   */
  async createUser(userData: Partial<User>): Promise<User> {
    const response = await this.post<User>('/users', userData);
    return response.data;
  }

  /**
   * Update an existing user.
   */
  async updateUser(id: number, userData: Partial<User>): Promise<User> {
    const response = await this.put<User>(`/users/${id}`, userData);
    return response.data;
  }

  /**
   * Delete a user by ID.
   */
  async deleteUser(id: number): Promise<void> {
    await this.delete(`/users/${id}`);
  }
}
"""
    )

    # File 6: Test file
    (repo_path / "tests" / "test_helpers.py").write_text(
        '''"""Tests for utility helper functions."""

import pytest
from datetime import datetime
from src.utils.helpers import (
    validate_email,
    sanitize_filename,
    format_timestamp,
    parse_csv_line,
    calculate_percentage,
    truncate_string,
    chunk_list,
)


class TestEmailValidation:
    """Tests for email validation function."""

    def test_valid_email(self):
        """Test that valid email addresses are accepted."""
        assert validate_email("user@example.com") is True
        assert validate_email("test.user@subdomain.example.com") is True

    def test_invalid_email(self):
        """Test that invalid email addresses are rejected."""
        assert validate_email("notanemail") is False
        assert validate_email("@example.com") is False
        assert validate_email("user@") is False


class TestFilenameeSanitization:
    """Tests for filename sanitization."""

    def test_remove_invalid_characters(self):
        """Test that invalid characters are removed."""
        result = sanitize_filename("file<>name.txt")
        assert "<" not in result
        assert ">" not in result

    def test_valid_filename_unchanged(self):
        """Test that valid filenames are not modified."""
        filename = "valid_filename.txt"
        assert sanitize_filename(filename) == filename


class TestTimestampFormatting:
    """Tests for timestamp formatting."""

    def test_format_custom_datetime(self):
        """Test formatting a specific datetime."""
        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = format_timestamp(dt)
        assert "2025-01-15" in result

    def test_format_none_uses_current_time(self):
        """Test that None uses current time."""
        result = format_timestamp()
        assert isinstance(result, str)
        assert len(result) > 0


class TestCSVParsing:
    """Tests for CSV line parsing."""

    def test_parse_simple_csv(self):
        """Test parsing a simple CSV line."""
        result = parse_csv_line("a,b,c")
        assert result == ["a", "b", "c"]

    def test_parse_with_spaces(self):
        """Test that spaces are trimmed."""
        result = parse_csv_line("a , b , c")
        assert result == ["a", "b", "c"]


class TestPercentageCalculation:
    """Tests for percentage calculation."""

    def test_calculate_percentage(self):
        """Test basic percentage calculation."""
        assert calculate_percentage(25, 100) == 25.0
        assert calculate_percentage(50, 200) == 25.0

    def test_zero_total_raises_error(self):
        """Test that zero total raises ValueError."""
        with pytest.raises(ValueError, match="zero total"):
            calculate_percentage(10, 0)


class TestStringTruncation:
    """Tests for string truncation."""

    def test_truncate_long_string(self):
        """Test truncating a string longer than max."""
        result = truncate_string("This is a long string", 10)
        assert len(result) == 10
        assert result.endswith("...")

    def test_short_string_unchanged(self):
        """Test that short strings are not truncated."""
        text = "Short"
        result = truncate_string(text, 10)
        assert result == text


class TestListChunking:
    """Tests for list chunking."""

    def test_chunk_list(self):
        """Test splitting list into chunks."""
        items = [1, 2, 3, 4, 5, 6, 7]
        result = chunk_list(items, 3)
        assert len(result) == 3
        assert result[0] == [1, 2, 3]
        assert result[2] == [7]

    def test_invalid_chunk_size(self):
        """Test that invalid chunk size raises error."""
        with pytest.raises(ValueError, match="at least 1"):
            chunk_list([1, 2, 3], 0)
'''
    )

    # File 7: README documentation
    (repo_path / "README.md").write_text(
        """# Application Documentation

## Overview

This application provides a web service for managing user data and processing requests.

## Features

- User authentication and management
- RESTful API endpoints
- Database integration with SQLite
- Real-time data processing
- Email validation and sanitization

## Installation

```bash
pip install -r requirements.txt
python src/app.py
```

## API Endpoints

### Users

- `GET /users` - List all users
- `GET /users/:id` - Get specific user
- `POST /users` - Create new user
- `PUT /users/:id` - Update user
- `DELETE /users/:id` - Delete user

### Authentication

- `POST /auth/login` - User login
- `POST /auth/logout` - User logout
- `POST /auth/refresh` - Refresh token

## Configuration

Create a `config.json` file:

```json
{
  "database_url": "sqlite:///app.db",
  "port": 8000,
  "debug": false
}
```

## Development

Run tests:

```bash
pytest tests/
```

Run linter:

```bash
flake8 src/
```

## Architecture

The application follows a layered architecture:

- **Models**: Data structures and database models
- **Utils**: Helper functions and utilities
- **API**: Request handlers and endpoints
- **Tests**: Unit and integration tests

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details
"""
    )

    # File 8: Configuration file
    (repo_path / "src" / "config.py").write_text(
        '''"""Application configuration management.

This module handles loading and validating application configuration.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


class Config:
    """Application configuration manager.

    Loads configuration from environment variables and config files.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to JSON configuration file
        """
        self.config_path = config_path or Path("config.json")
        self._data: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file and environment."""
        # Load from file if it exists
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._data = json.load(f)

        # Override with environment variables
        env_overrides = {
            "DATABASE_URL": "database_url",
            "PORT": "port",
            "DEBUG": "debug",
            "SECRET_KEY": "secret_key",
        }

        for env_var, config_key in env_overrides.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert types as needed
                if config_key == "port":
                    value = int(value)
                elif config_key == "debug":
                    value = value.lower() in ('true', '1', 'yes')
                self._data[config_key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        """Get required configuration value.

        Args:
            key: Configuration key

        Returns:
            Configuration value

        Raises:
            ConfigurationError: If key is not found
        """
        if key not in self._data:
            raise ConfigurationError(f"Required configuration key missing: {key}")
        return self._data[key]

    @property
    def database_url(self) -> str:
        """Get database URL."""
        return self.get("database_url", "sqlite:///default.db")

    @property
    def port(self) -> int:
        """Get server port."""
        return self.get("port", 8000)

    @property
    def debug(self) -> bool:
        """Get debug mode flag."""
        return self.get("debug", False)

    def validate(self) -> None:
        """Validate configuration values.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Check port is valid
        port = self.port
        if not (1 <= port <= 65535):
            raise ConfigurationError(f"Invalid port number: {port}")

        # Check database URL is set
        if not self.database_url:
            raise ConfigurationError("Database URL cannot be empty")
'''
    )

    # File 9: Database module
    (repo_path / "src" / "database.py").write_text(
        '''"""Database connection and query execution.

This module provides database access functionality.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


class DatabaseError(Exception):
    """Raised when database operations fail."""

    pass


class Database:
    """Database connection manager for SQLite.

    Provides methods for executing queries and managing transactions.
    """

    def __init__(self, db_path: Path):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish database connection."""
        try:
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to database: {e}")

    def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions.

        Yields:
            Database connection within transaction

        Raises:
            DatabaseError: If transaction fails
        """
        if not self._connection:
            raise DatabaseError("Not connected to database")

        try:
            yield self._connection
            self._connection.commit()
        except sqlite3.Error as e:
            self._connection.rollback()
            raise DatabaseError(f"Transaction failed: {e}")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Cursor with query results

        Raises:
            DatabaseError: If query execution fails
        """
        if not self._connection:
            raise DatabaseError("Not connected to database")

        try:
            cursor = self._connection.cursor()
            cursor.execute(query, params)
            return cursor
        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}")

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row from query results.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Dictionary with row data, or None if no results
        """
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows from query results.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            List of dictionaries with row data
        """
        cursor = self.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def initialize_schema(self) -> None:
        """Create database tables if they don't exist."""
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            last_login TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        """

        with self.transaction():
            for statement in schema.split(';'):
                if statement.strip():
                    self.execute(statement)
'''
    )

    # File 10: Additional utility module
    (repo_path / "src" / "utils" / "validators.py").write_text(
        '''"""Data validation utilities.

Provides functions for validating various data types and formats.
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL.

    Args:
        url: URL string to validate

    Returns:
        True if URL is valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_valid_port(port: Any) -> bool:
    """Check if value is a valid port number.

    Args:
        port: Port value to validate

    Returns:
        True if port is valid (1-65535), False otherwise
    """
    try:
        port_int = int(port)
        return 1 <= port_int <= 65535
    except (ValueError, TypeError):
        return False


def is_valid_username(username: str, min_length: int = 3, max_length: int = 32) -> bool:
    """Check if username meets requirements.

    Args:
        username: Username to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length

    Returns:
        True if username is valid, False otherwise
    """
    if not username or not isinstance(username, str):
        return False

    if len(username) < min_length or len(username) > max_length:
        return False

    # Must start with letter, contain only alphanumeric and underscore
    pattern = r'^[a-zA-Z][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, username))


def validate_required_fields(data: Dict[str, Any], required: List[str]) -> List[str]:
    """Check for missing required fields in dictionary.

    Args:
        data: Dictionary to validate
        required: List of required field names

    Returns:
        List of missing field names (empty if all present)
    """
    missing = []
    for field in required:
        if field not in data or data[field] is None:
            missing.append(field)
    return missing


def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """Sanitize user input by removing dangerous characters.

    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text string
    """
    if not text:
        return ""

    # Remove control characters except newline and tab
    sanitized = ''.join(char for char in text if char.isprintable() or char in '\\n\\t')

    # Truncate if needed
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized.strip()


def is_safe_path(path: str, base_dir: str) -> bool:
    """Check if file path is safe (no directory traversal).

    Args:
        path: File path to validate
        base_dir: Base directory that path must be within

    Returns:
        True if path is safe, False if it tries to escape base_dir
    """
    from pathlib import Path

    try:
        base = Path(base_dir).resolve()
        target = (base / path).resolve()
        return target.is_relative_to(base)
    except (ValueError, RuntimeError):
        return False
'''
    )

    # Commit all files
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, timeout=5, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with realistic test data"],
        cwd=repo_path,
        check=True,
        timeout=5,
        capture_output=True,
    )

    return repo_path
