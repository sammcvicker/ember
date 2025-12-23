"""CLI output assertion helpers for reducing test brittleness.

These helpers prioritize semantic assertions (exit codes, file existence) over
exact string matching. When output validation is necessary, they use regex
patterns to be resilient to cosmetic changes like emoji or wording updates.

Rationale (Issue #330, Issue #360):
- Exact string matches break when emojis change or messages are reworded
- Tests should validate behavior, not presentation
- Regex patterns allow flexibility while still verifying key content

Available helpers:
- assert_command_success/failed: Exit code validation
- assert_output_matches/contains: Pattern and substring matching
- assert_error_message/success_indicator: Error and success detection
- assert_files_created: Semantic file existence checks
- assert_has_line_numbers: Line number format detection
- assert_has_rank_indicators: Result ranking format detection
- assert_has_separator: Output separator detection
- assert_result_list_format: High-level result format validation
"""

import re
from pathlib import Path

from click.testing import Result


def assert_command_success(result: Result, *, context: str = "") -> None:
    """Assert that a CLI command succeeded.

    Checks exit code is 0 and provides helpful error message on failure.

    Args:
        result: Click test runner Result object.
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["init"])
        assert_command_success(result, context="ember init")
    """
    ctx = f" ({context})" if context else ""
    assert result.exit_code == 0, (
        f"Command failed{ctx}:\n"
        f"  Exit code: {result.exit_code}\n"
        f"  Output: {result.output[:500]}"
    )


def assert_command_failed(
    result: Result,
    *,
    expected_code: int = 1,
    context: str = "",
) -> None:
    """Assert that a CLI command failed with expected exit code.

    Args:
        result: Click test runner Result object.
        expected_code: Expected non-zero exit code (default: 1).
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["sync"])  # Without init
        assert_command_failed(result, context="sync without init")
    """
    ctx = f" ({context})" if context else ""
    assert result.exit_code == expected_code, (
        f"Expected command to fail{ctx} with code {expected_code}, "
        f"but got {result.exit_code}:\n"
        f"  Output: {result.output[:500]}"
    )


def assert_output_matches(
    result: Result,
    pattern: str,
    *,
    flags: int = 0,
    context: str = "",
) -> re.Match[str]:
    """Assert that output matches a regex pattern.

    Use this for output validation that must be checked but should be
    resilient to cosmetic changes. Prefer semantic assertions when possible.

    Args:
        result: Click test runner Result object.
        pattern: Regex pattern to match against output.
        flags: Regex flags (e.g., re.IGNORECASE).
        context: Optional context string for error messages.

    Returns:
        The regex Match object for further inspection if needed.

    Example:
        # Matches "Indexed 5 files" or "Indexed 10 files"
        assert_output_matches(result, r"Indexed \\d+ files?")

        # Case-insensitive matching
        assert_output_matches(result, r"error", flags=re.IGNORECASE)
    """
    ctx = f" ({context})" if context else ""
    match = re.search(pattern, result.output, flags)
    assert match is not None, (
        f"Pattern not found{ctx}:\n"
        f"  Pattern: {pattern}\n"
        f"  Output: {result.output[:500]}"
    )
    return match


def assert_output_contains(
    result: Result,
    *substrings: str,
    case_sensitive: bool = True,
    context: str = "",
) -> None:
    """Assert that output contains all specified substrings.

    Use when exact substring matching is appropriate (e.g., file paths,
    command names). For flexible matching, use assert_output_matches.

    Args:
        result: Click test runner Result object.
        *substrings: One or more substrings that must appear in output.
        case_sensitive: Whether to do case-sensitive matching.
        context: Optional context string for error messages.

    Example:
        # Check error message contains key information
        assert_output_contains(result, "Error", "ember init")
    """
    ctx = f" ({context})" if context else ""
    output = result.output if case_sensitive else result.output.lower()

    for substring in substrings:
        check = substring if case_sensitive else substring.lower()
        assert check in output, (
            f"Substring not found{ctx}:\n"
            f"  Expected: {substring!r}\n"
            f"  Output: {result.output[:500]}"
        )


def assert_error_message(result: Result, *, hint: str | None = None) -> None:
    """Assert that output contains an error indication.

    Checks for common error patterns without requiring exact message match.
    Optionally checks for a specific hint in the output.

    Args:
        result: Click test runner Result object (should have non-zero exit code).
        hint: Optional substring that should appear as a hint (e.g., "ember init").

    Example:
        result = runner.invoke(cli, ["sync"])  # Without init
        assert_command_failed(result)
        assert_error_message(result, hint="ember init")
    """
    # Check for error indication - case insensitive
    has_error = re.search(r"error", result.output, re.IGNORECASE) is not None
    assert has_error, (
        f"Expected error message in output:\n"
        f"  Output: {result.output[:500]}"
    )

    if hint:
        assert hint in result.output, (
            f"Expected hint '{hint}' in error output:\n"
            f"  Output: {result.output[:500]}"
        )


def assert_success_indicator(result: Result) -> None:
    """Assert that output contains a success indicator.

    Checks for common success patterns (checkmark emoji, "success", "completed")
    without requiring exact match.

    Args:
        result: Click test runner Result object.

    Example:
        result = runner.invoke(cli, ["init"])
        assert_command_success(result)
        assert_success_indicator(result)
    """
    # Check for common success indicators
    success_patterns = [
        r"[✓✔]",  # Checkmark emojis
        r"success",
        r"completed",
        r"initialized",
        r"indexed",
    ]
    pattern = "|".join(success_patterns)
    has_success = re.search(pattern, result.output, re.IGNORECASE) is not None
    assert has_success, (
        f"Expected success indicator in output:\n"
        f"  Output: {result.output[:500]}"
    )


def assert_files_created(
    base_path: Path,
    *relative_paths: str,
) -> None:
    """Assert that files were created at specified paths.

    Semantic assertion that verifies files exist rather than checking
    output messages about file creation.

    Args:
        base_path: Base directory path.
        *relative_paths: Relative paths to check for existence.

    Example:
        # Instead of: assert "Created config.toml" in result.output
        assert_files_created(
            repo_path / ".ember",
            "config.toml",
            "index.db",
            "state.json",
        )
    """
    for rel_path in relative_paths:
        full_path = base_path / rel_path
        assert full_path.exists(), f"Expected file not created: {full_path}"


def assert_has_line_numbers(result: Result, *, context: str = "") -> None:
    """Assert that output contains line numbers in standard format.

    Checks for common line number patterns used in code output:
    - Leading digit with separator (e.g., "  1 |", "  1:", "1:")
    - Rich-style line numbers (padded numbers at line start)

    This is resilient to formatting changes (spacing, separator style).

    Args:
        result: Click test runner Result object.
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["cat", "1"])
        assert_has_line_numbers(result, context="cat output")
    """
    ctx = f" ({context})" if context else ""

    # Check for various line number formats:
    # - "  1 |" or "  1|" (pipe separator)
    # - "  1:" or "1:" (colon separator)
    # - Lines starting with padded numbers (Rich format)
    line_number_pattern = r"^\s*\d+\s*[|:]|^\s+\d+\s+\S"

    lines = result.output.split("\n")
    has_line_numbers = any(re.match(line_number_pattern, line) for line in lines)

    assert has_line_numbers, (
        f"Expected line numbers in output{ctx}:\n"
        f"  Pattern: {line_number_pattern}\n"
        f"  First 5 lines: {lines[:5]}"
    )


def assert_has_rank_indicators(result: Result, *, context: str = "") -> None:
    """Assert that output contains result rank indicators like [1], [2], etc.

    Resilient to:
    - Different bracket styles ([1] vs (1) vs #1)
    - Spacing variations

    Args:
        result: Click test runner Result object.
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["find", "query", "--context", "3"])
        assert_has_rank_indicators(result)
    """
    ctx = f" ({context})" if context else ""

    # Match [N], (N), #N, or "Result N" patterns
    rank_pattern = r"\[\d+\]|\(\d+\)|#\d+|[Rr]esult\s+\d+"
    has_ranks = re.search(rank_pattern, result.output) is not None

    assert has_ranks, (
        f"Expected rank indicators in output{ctx}:\n"
        f"  Pattern: {rank_pattern}\n"
        f"  Output: {result.output[:500]}"
    )


def assert_has_separator(
    result: Result,
    separator: str = "|",
    *,
    context: str = "",
) -> None:
    """Assert that output uses a specific separator character.

    Use for checking output format uses expected separators (|, :, etc.)
    without being brittle to exact positioning.

    Args:
        result: Click test runner Result object.
        separator: The separator character to look for.
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["cat", "1", "--context", "2"])
        assert_has_separator(result, "|", context="context output")
    """
    ctx = f" ({context})" if context else ""

    assert separator in result.output, (
        f"Expected separator '{separator}' in output{ctx}:\n"
        f"  Output: {result.output[:500]}"
    )


def assert_result_list_format(
    result: Result,
    *,
    expect_line_numbers: bool = True,
    expect_ranks: bool = False,
    context: str = "",
) -> None:
    """Assert that output follows expected result list format.

    High-level semantic check for search/find result formatting.
    Validates structure without checking exact text.

    Args:
        result: Click test runner Result object.
        expect_line_numbers: Whether line numbers should be present.
        expect_ranks: Whether rank indicators ([1], [2]) should be present.
        context: Optional context string for error messages.

    Example:
        result = runner.invoke(cli, ["find", "query", "--context", "3"])
        assert_result_list_format(result, expect_line_numbers=True, expect_ranks=True)
    """
    ctx = f" ({context})" if context else ""

    # Skip empty results
    if not result.output.strip() or "No results" in result.output:
        return

    if expect_line_numbers:
        assert_has_line_numbers(result, context=f"result list{ctx}")

    if expect_ranks:
        assert_has_rank_indicators(result, context=f"result list{ctx}")
