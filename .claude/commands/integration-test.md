# Comprehensive Integration Testing

You are performing end-to-end integration testing of Ember to verify all functionality works correctly after installation.

## Phase 1: Reinstall Ember

First, build and reinstall Ember from source:

```bash
bash reinstall.sh
```

Verify the installation succeeded by checking the version:

```bash
ember --version
```

## Phase 2: Test Environment Setup

Create a clean test repository in a temporary directory:

```bash
# Create temp directory with timestamp to avoid conflicts
TEST_DIR="/tmp/ember-integration-test-$(date +%s)"
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

# Initialize git repo (required for Ember)
git init
git config user.email "test@example.com"
git config user.name "Test User"
```

Create diverse test files to exercise different language parsers and features:

```bash
# Python file with functions and classes
cat > main.py << 'EOF'
"""Main module for testing."""

def calculate_sum(a: int, b: int) -> int:
    """Calculate sum of two numbers."""
    return a + b

class DataProcessor:
    """Process data efficiently."""

    def __init__(self, name: str):
        self.name = name

    def process(self, data: list) -> dict:
        """Process the input data."""
        return {"name": self.name, "count": len(data)}

API_KEY = "test-key-12345"
EOF

# JavaScript/TypeScript file
cat > utils.ts << 'EOF'
// Utility functions for the app

export function formatDate(date: Date): string {
    return date.toISOString();
}

export class Logger {
    private prefix: string;

    constructor(prefix: string) {
        this.prefix = prefix;
    }

    log(message: string): void {
        console.log(`${this.prefix}: ${message}`);
    }
}

const config = {
    apiUrl: "https://api.example.com",
    timeout: 5000
};
EOF

# Go file
cat > server.go << 'EOF'
package main

import "fmt"

// StartServer initializes and starts the HTTP server
func StartServer(port int) error {
    fmt.Printf("Starting server on port %d\n", port)
    return nil
}

type Config struct {
    Host string
    Port int
}

func main() {
    cfg := Config{Host: "localhost", Port: 8080}
    StartServer(cfg.Port)
}
EOF

# Rust file
cat > lib.rs << 'EOF'
/// Calculate fibonacci number recursively
pub fn fibonacci(n: u32) -> u64 {
    match n {
        0 => 0,
        1 => 1,
        _ => fibonacci(n - 1) + fibonacci(n - 2),
    }
}

pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }
}
EOF

# Java file
cat > App.java << 'EOF'
public class App {
    private String name;

    public App(String name) {
        this.name = name;
    }

    public void run() {
        System.out.println("Running: " + name);
    }

    public static void main(String[] args) {
        App app = new App("TestApp");
        app.run();
    }
}
EOF

# Create a subdirectory with more files
mkdir -p src/helpers

cat > src/helpers/math.py << 'EOF'
"""Math helper functions."""

def multiply(x: float, y: float) -> float:
    """Multiply two numbers."""
    return x * y

def divide(x: float, y: float) -> float:
    """Divide two numbers."""
    if y == 0:
        raise ValueError("Cannot divide by zero")
    return x / y
EOF

# Commit all files
git add -A
git commit -m "Initial test files"
```

## Phase 3: Test Ember Initialization

Test the `ember init` command:

```bash
# Test basic init
ember init

# Verify .ember directory was created
ls -la .ember/

# Check that required files exist
test -f .ember/config.toml && echo "✓ config.toml exists" || echo "✗ config.toml missing"
test -f .ember/index.db && echo "✓ index.db exists" || echo "✗ index.db missing"
test -f .ember/state.json && echo "✓ state.json exists" || echo "✗ state.json missing"

# Verify config has expected structure
cat .ember/config.toml
```

Test that re-init without --force fails:

```bash
# Should fail
ember init 2>&1 | grep -q "already exists" && echo "✓ Correctly prevents re-init" || echo "✗ Should have prevented re-init"
```

Test force re-initialization:

```bash
# Should succeed
ember init --force

# Verify it reports reinitialization
```

## Phase 4: Test Indexing (Sync)

Test basic sync:

```bash
# Run sync and capture output
ember sync

# Verify it indexed files
ember find "calculate sum" --json | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'✓ Search works: {len(data)} results')"
```

Test incremental sync (no changes):

```bash
# Sync again - should report no changes
ember sync 2>&1 | grep -q "No changes detected" && echo "✓ Incremental sync detected no changes" || echo "✗ Should detect no changes"
```

Test sync after file changes:

```bash
# Modify a file
echo "" >> main.py
echo "def new_function(): pass" >> main.py
git add main.py
git commit -m "Add new function"

# Sync again - should detect changes
ember sync 2>&1 | grep -q "Indexed" && echo "✓ Detected file changes" || echo "✗ Should detect changes"
```

Test full reindex:

```bash
# Force full reindex
ember sync --reindex 2>&1 | grep -q "full sync" && echo "✓ Full reindex works" || echo "✗ Full reindex failed"
```

Test sync modes:

```bash
# Test staged mode (add uncommitted change)
echo "# comment" >> utils.ts
git add utils.ts

ember sync --staged
echo "✓ Staged sync completed"

# Commit the change
git commit -m "Add comment"
```

## Phase 5: Test Search (Find)

Test basic search:

```bash
# Search for Python function
ember find "calculate sum"
echo "---"

# Search for class
ember find "DataProcessor"
echo "---"

# Search for TypeScript function
ember find "formatDate"
echo "---"

# Search for Go function
ember find "StartServer"
echo "---"
```

Test JSON output:

```bash
# Get JSON results
RESULT_COUNT=$(ember find "function" --json | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
echo "✓ Found $RESULT_COUNT results for 'function' (JSON mode)"
```

Test topk parameter:

```bash
# Limit results
ember find "function" -k 3 --json | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'✓ topk works: {len(data)} results (expected ≤3)')"
```

Test path filtering:

```bash
# Filter by path pattern
ember find "multiply" --in "src/**/*.py"
echo "---"

# Should find in src/helpers/math.py only
ember find "multiply" --in "src/**" --json | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'✓ Path filter: {len(data)} results')"
```

Test language filtering:

```bash
# Filter by language
ember find "function" --lang py
echo "---"

ember find "function" --lang ts
echo "---"

ember find "function" --lang go
echo "---"
```

Test auto-sync on search:

```bash
# Make an uncommitted change
echo "# new comment" >> main.py

# Search should auto-sync
ember find "calculate" 2>&1 | grep -q "Synced" && echo "✓ Auto-sync triggered" || echo "✓ Index was up to date or auto-sync happened silently"

# Revert change
git restore main.py
```

Test --no-sync flag:

```bash
# Make change
echo "# test" >> main.py

# Search without sync
ember find "test" --no-sync
echo "✓ --no-sync works"

# Restore
git restore main.py
```

## Phase 6: Test Cat Command

Test displaying search results:

```bash
# Search first to populate cache
ember find "DataProcessor" > /dev/null

# Display first result
ember cat 1
echo "---"

# Display with context
ember cat 1 -C 3
echo "---"
```

Test cat error handling:

```bash
# Invalid index
ember cat 999 2>&1 | grep -q "out of range" && echo "✓ Handles invalid index" || echo "✗ Should handle invalid index"

# No search cache
rm -f .ember/.last_search.json
ember cat 1 2>&1 | grep -q "No recent search" && echo "✓ Handles missing cache" || echo "✗ Should handle missing cache"
```

## Phase 7: Test Open Command (if possible)

**Note:** The `open` command requires an interactive editor, so we'll just verify it handles errors correctly:

```bash
# Repopulate search cache
ember find "calculate" > /dev/null

# Test with invalid index
ember open 999 2>&1 | grep -q "out of range" && echo "✓ Open handles invalid index" || echo "✗ Should handle invalid index"

# Note: Cannot test actual editor opening in non-interactive mode
echo "⚠ Note: Actual editor opening not tested (requires interactive session)"
```

## Phase 8: Test Configuration

Test that config.toml is respected:

```bash
# Read current config
cat .ember/config.toml

# Modify topk default
sed -i.bak 's/topk = 5/topk = 15/' .ember/config.toml

# Search without -k flag should use config default
RESULT_COUNT=$(ember find "function" --json | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
echo "✓ Config change: Found $RESULT_COUNT results (should respect config topk if many matches)"

# Restore config
mv .ember/config.toml.bak .ember/config.toml
```

## Phase 9: Test Error Handling

Test commands without initialization:

```bash
# Create new directory without ember
cd /tmp
TEST_DIR_2="/tmp/ember-no-init-$(date +%s)"
mkdir -p "$TEST_DIR_2"
cd "$TEST_DIR_2"
git init

# Sync should fail
ember sync 2>&1 | grep -q "not initialized" && echo "✓ Sync requires init" || echo "✗ Should require init"

# Find should fail
ember find "test" 2>&1 | grep -q "not initialized" && echo "✓ Find requires init" || echo "✗ Should require init"

# Go back to test directory
cd "$TEST_DIR"
```

Test non-git directory:

```bash
# Create directory without git
TEST_DIR_3="/tmp/ember-no-git-$(date +%s)"
mkdir -p "$TEST_DIR_3"
cd "$TEST_DIR_3"

# Init should work
ember init

# But sync should fail (no git repo)
ember sync 2>&1 | grep -q -i "git\|repository" && echo "✓ Sync detects missing git" || echo "⚠ Sync behavior with no git"

# Go back
cd "$TEST_DIR"
```

## Phase 10: Performance Check (Optional)

Quick performance spot-check:

```bash
# Time a sync operation
echo "Timing sync performance..."
time ember sync --reindex

# Time a search operation
echo "Timing search performance..."
time ember find "function class" > /dev/null
```

## Phase 11: Cleanup

```bash
# Go back to original directory
cd /Users/sammcvicker/projects/ember

# Cleanup note
echo ""
echo "Test directories created:"
echo "  - $TEST_DIR"
echo "  - $TEST_DIR_2 (if created)"
echo "  - $TEST_DIR_3 (if created)"
echo ""
echo "These can be safely deleted with: rm -rf /tmp/ember-*-test-*"
```

## Important Notes

**What Cannot Be Tested:**
- Progress bars (they use `transient=True` and disappear when complete)
- Interactive editor opening (requires user interaction)
- Visual styling/colors (output formatting is environment-dependent)
- Actual embedding quality (requires human evaluation)

**What IS Tested:**
- All CLI commands (init, sync, find, cat, open error handling)
- JSON output parsing and validation
- File creation and database initialization
- Incremental sync detection
- Search result caching for cat/open
- Path and language filters
- Configuration loading
- Error handling for edge cases
- Git integration (commits, staged files, worktree)

## Success Criteria

A successful test run should show:
- ✓ All commands execute without crashes
- ✓ Init creates required files (.ember directory structure)
- ✓ Sync correctly indexes files and detects changes
- ✓ Incremental sync detects when no changes exist
- ✓ Find returns relevant results in both text and JSON modes
- ✓ Filters (--in, --lang, -k) work correctly
- ✓ Cat command displays cached results
- ✓ Error handling works for invalid inputs
- ✓ Config changes are respected
- ✓ Auto-sync triggers when index is stale

## Reflection Prompt

After completing all tests, reflect on:
1. **What passed:** List all successful test cases
2. **What failed:** Any commands that errored or produced unexpected output
3. **Performance:** Were sync and search operations reasonably fast?
4. **Edge cases:** Did error handling work as expected?
5. **User experience:** Is the CLI output clear and helpful?
6. **Regression risks:** Any behavior that differs from expected functionality?

Report findings in a structured summary with specific command outputs for any failures.

---

**Remember:** This is a functional test, not a fix session. Document issues but don't modify code unless explicitly asked to fix something.
