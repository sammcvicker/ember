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

# TypeScript file with interfaces, type aliases, and arrow functions (NEW in v1.2.0)
cat > utils.ts << 'EOF'
// Utility functions for the app

// Interface definition (NEW: should be extracted)
export interface Logger {
    prefix: string;
    log(message: string): void;
}

// Type alias (NEW: should be extracted)
export type Status = 'active' | 'inactive' | 'pending';

// Generic type alias
export type Handler<T> = (event: T) => void;

// Named arrow function (NEW: should be extracted with name)
export const formatDate = (date: Date): string => {
    return date.toISOString();
};

// Async arrow function
export const fetchData = async (url: string): Promise<Response> => {
    return fetch(url);
};

// Traditional class
export class UserService {
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

# Go file with struct and interface definitions (NEW in v1.2.0)
cat > server.go << 'EOF'
package main

import "fmt"

// StartServer initializes and starts the HTTP server
func StartServer(port int) error {
    fmt.Printf("Starting server on port %d\n", port)
    return nil
}

// Config struct definition (NEW: should be extracted)
type Config struct {
    Host string
    Port int
}

// Server interface definition (NEW: should be extracted)
type Server interface {
    Start() error
    Stop() error
}

// Generic container (Go 1.18+)
type Container[T any] struct {
    Value T
}

func main() {
    cfg := Config{Host: "localhost", Port: 8080}
    StartServer(cfg.Port)
}
EOF

# Rust file with struct, enum, and trait definitions (NEW in v1.2.0)
cat > lib.rs << 'EOF'
/// Calculate fibonacci number recursively
pub fn fibonacci(n: u32) -> u64 {
    match n {
        0 => 0,
        1 => 1,
        _ => fibonacci(n - 1) + fibonacci(n - 2),
    }
}

/// Point struct (NEW: should be extracted)
pub struct Point {
    pub x: f64,
    pub y: f64,
}

/// Status enum (NEW: should be extracted)
pub enum Status {
    Active,
    Inactive,
    Pending,
}

/// Display trait (NEW: should be extracted)
pub trait Display {
    fn display(&self) -> String;
}

impl Point {
    pub fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }
}

impl Display for Point {
    fn display(&self) -> String {
        format!("({}, {})", self.x, self.y)
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
# Test basic init (will auto-detect hardware and recommend model)
ember init --yes

# Verify .ember directory was created
ls -la .ember/

# Check that required files exist (NOTE: state.json was removed in v1.2.0+)
test -f .ember/config.toml && echo "✓ config.toml exists" || echo "✗ config.toml missing"
test -f .ember/index.db && echo "✓ index.db exists" || echo "✗ index.db missing"
test ! -f .ember/state.json && echo "✓ state.json correctly absent (removed in v1.2.0)" || echo "⚠ state.json present (legacy)"

# Verify config has expected structure
cat .ember/config.toml
```

Test that re-init without --force fails:

```bash
# Should fail
ember init 2>&1 | grep -q "already" && echo "✓ Correctly prevents re-init" || echo "✗ Should have prevented re-init"
```

Test force re-initialization:

```bash
# Should succeed
ember init --force --yes

# Verify it reports reinitialization
```

Test init with specific model selection:

```bash
# Create a new test directory for model testing
TEST_DIR_MODEL="/tmp/ember-model-test-$(date +%s)"
mkdir -p "$TEST_DIR_MODEL"
cd "$TEST_DIR_MODEL"
git init
git config user.email "test@example.com"
git config user.name "Test User"

# Test init with minilm model (lightweight option)
ember init --model minilm --yes

# Verify config contains minilm
grep -q "minilm" .ember/config.toml && echo "✓ MiniLM model configured" || echo "✗ Model not set correctly"

cd "$TEST_DIR"
```

## Phase 4: Test Config Command Group (NEW in v1.2.0)

Test the new `ember config` command group:

```bash
# Test config show - displays all config locations and merged settings
ember config show
echo "---"

# Test config show with specific scopes
ember config show --local
echo "---"

ember config show --global
echo "---"

ember config show --effective
echo "---"

# Test config path commands
ember config path --local
ember config path --global
echo "---"

# Note: ember config edit opens an editor, cannot test non-interactively
echo "⚠ Note: 'ember config edit' requires interactive session (opens editor)"
```

## Phase 5: Test Status Command

Test the `ember status` command to check index freshness:

```bash
# Run initial sync
ember sync

# Check status - should report current/up-to-date
ember status

# Verify status output contains expected info
ember status 2>&1 | grep -qE "(current|up.to.date|synced)" && echo "✓ Status reports current" || echo "✗ Status unclear"

# Make a change
echo "# new line" >> main.py
git add main.py
git commit -m "Add line"

# Check status - should report stale/out-of-date
ember status 2>&1 | grep -qE "(stale|out.of.date|needs)" && echo "✓ Status detects stale index" || echo "✗ Should detect staleness"

# Sync again
ember sync

# Status should be current again
ember status
```

## Phase 6: Test Indexing (Sync)

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
ember sync 2>&1 | grep -qE "(No changes|up.to.date|Already)" && echo "✓ Incremental sync detected no changes" || echo "✗ Should detect no changes"
```

Test sync after file changes:

```bash
# Modify a file
echo "" >> main.py
echo "def new_function(): pass" >> main.py
git add main.py
git commit -m "Add new function"

# Sync again - should detect changes
ember sync 2>&1 | grep -qE "(Indexed|Updated|files)" && echo "✓ Detected file changes" || echo "✗ Should detect changes"
```

Test full reindex:

```bash
# Force full reindex
ember sync --reindex 2>&1 | grep -qE "(full|reindex|all)" && echo "✓ Full reindex works" || echo "⚠ Verify reindex behavior"
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

## Phase 7: Test Search (Find)

Test basic search:

```bash
# Search for Python function
ember find "calculate sum"
echo "---"

# Search for class
ember find "DataProcessor"
echo "---"

# Search for TypeScript interface (NEW in v1.2.0)
ember find "Logger"
echo "---"

# Search for TypeScript type alias (NEW in v1.2.0)
ember find "Status"
echo "---"

# Search for TypeScript arrow function (NEW in v1.2.0)
ember find "formatDate"
echo "---"

# Search for Go struct (NEW in v1.2.0)
ember find "Config"
echo "---"

# Search for Go interface (NEW in v1.2.0)
ember find "Server interface"
echo "---"

# Search for Rust struct (NEW in v1.2.0)
ember find "Point"
echo "---"

# Search for Rust enum (NEW in v1.2.0)
ember find "Status enum"
echo "---"

# Search for Rust trait (NEW in v1.2.0)
ember find "Display trait"
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

# Test with PATH argument (alternative to --in)
ember find "multiply" src/
echo "---"
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

ember find "function" --lang rs
echo "---"
```

Test auto-sync on search:

```bash
# Make an uncommitted change
echo "# new comment" >> main.py

# Search should auto-sync
ember find "calculate" 2>&1 | grep -qE "(Sync|sync|index)" && echo "✓ Auto-sync triggered" || echo "✓ Index was up to date"

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

## Phase 8: Test Cat Command with Syntax Highlighting

Test displaying search results with syntax highlighting:

```bash
# Search first to populate cache
ember find "DataProcessor" > /dev/null

# Display first result (should have syntax highlighting)
ember cat 1
echo "---"

# Display with context (also syntax highlighted)
ember cat 1 -C 5
echo "---"

# Test different languages for syntax highlighting
ember find "fibonacci" > /dev/null
ember cat 1
echo "---"

ember find "StartServer" > /dev/null
ember cat 1
echo "---"
```

Test cat error handling:

```bash
# Invalid index
ember cat 999 2>&1 | grep -qE "(out of range|invalid|not found)" && echo "✓ Handles invalid index" || echo "✗ Should handle invalid index"

# No search cache
rm -f .ember/.last_search.json
ember cat 1 2>&1 | grep -qE "(No recent|search first|no results)" && echo "✓ Handles missing cache" || echo "✗ Should handle missing cache"
```

## Phase 9: Test Interactive Search TUI (ember search)

**Note:** The `ember search` TUI is interactive and cannot be fully automated. Test manually:

```bash
# Note: These commands launch an interactive TUI
# Press Ctrl+C to exit each one after verifying it works

echo "Manual tests for interactive search TUI:"
echo "1. Run: ember search"
echo "   - Type a query and verify results appear"
echo "   - Use arrow keys to navigate"
echo "   - Press Enter to view a result in preview pane"
echo "   - Press 'e' to open in editor"
echo ""
echo "2. Run: ember search src/"
echo "   - Should restrict search to src/ directory"
echo ""
echo "3. Run: ember search --in '*.py'"
echo "   - Should restrict search to Python files"
echo ""
echo "⚠ Note: Interactive TUI testing requires manual interaction"
```

## Phase 10: Test Open Command

Test the open command error handling:

```bash
# Repopulate search cache
ember find "calculate" > /dev/null

# Test with invalid index
ember open 999 2>&1 | grep -qE "(out of range|invalid|not found)" && echo "✓ Open handles invalid index" || echo "✗ Should handle invalid index"

# Note: Cannot test actual editor opening in non-interactive mode
echo "⚠ Note: Actual editor opening not tested (requires interactive session)"
```

## Phase 11: Test Configuration Behavior

Test that config.toml is respected:

```bash
# Read current config
cat .ember/config.toml

# Backup config
cp .ember/config.toml .ember/config.toml.bak

# Modify topk default
cat > .ember/config.toml << 'EOF'
[search]
topk = 15
EOF

# Search without -k flag should use config default
RESULT_COUNT=$(ember find "function" --json | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
echo "✓ Config change: Found $RESULT_COUNT results (should respect config topk if many matches)"

# Restore config
mv .ember/config.toml.bak .ember/config.toml
```

Test global config interaction:

```bash
# Check global config path
GLOBAL_CONFIG=$(ember config path --global)
echo "Global config path: $GLOBAL_CONFIG"

# Check if global config exists
test -f "$GLOBAL_CONFIG" && echo "✓ Global config exists" || echo "ℹ No global config (will use defaults)"

# Show effective (merged) config
ember config show --effective
```

## Phase 12: Test Error Handling

Test commands without initialization:

```bash
# Create new directory without ember
cd /tmp
TEST_DIR_2="/tmp/ember-no-init-$(date +%s)"
mkdir -p "$TEST_DIR_2"
cd "$TEST_DIR_2"
git init
git config user.email "test@example.com"
git config user.name "Test User"

# Sync should fail
ember sync 2>&1 | grep -qE "(not initialized|init first|no ember)" && echo "✓ Sync requires init" || echo "✗ Should require init"

# Find should fail
ember find "test" 2>&1 | grep -qE "(not initialized|init first|no ember)" && echo "✓ Find requires init" || echo "✗ Should require init"

# Status should fail
ember status 2>&1 | grep -qE "(not initialized|init first|no ember)" && echo "✓ Status requires init" || echo "✗ Should require init"

# Go back to test directory
cd "$TEST_DIR"
```

Test dimension mismatch detection (model change):

```bash
# This tests the early detection of model mismatches
# Create a new test repo
TEST_DIR_DIM="/tmp/ember-dim-test-$(date +%s)"
mkdir -p "$TEST_DIR_DIM"
cd "$TEST_DIR_DIM"
git init
git config user.email "test@example.com"
git config user.name "Test User"
echo "test file" > test.txt
git add -A && git commit -m "init"

# Init with one model
ember init --model minilm --yes
ember sync

# Now try to change the model in config
sed -i.bak 's/minilm/jina-code-v2/' .ember/config.toml 2>/dev/null || \
  sed -i '' 's/minilm/jina-code-v2/' .ember/config.toml

# Sync should fail with dimension mismatch
ember sync 2>&1 | grep -qE "(mismatch|different model|dimension|incompatible)" && echo "✓ Dimension mismatch detected" || echo "⚠ Check dimension mismatch behavior"

cd "$TEST_DIR"
```

## Phase 13: Test Daemon (if applicable)

Test daemon commands:

```bash
# Stop any running daemon first
ember daemon stop 2>/dev/null

# Start daemon
ember daemon start

# Check status
ember daemon status | grep -qE "(running|active)" && echo "✓ Daemon started" || echo "⚠ Daemon status unclear"

# Verify search works with daemon
ember find "calculate" --json | python3 -c "import sys, json; data = json.load(sys.stdin); print(f'✓ Search with daemon: {len(data)} results')"

# Stop daemon
ember daemon stop

# Verify stopped
ember daemon status | grep -qE "(stopped|not running|inactive)" && echo "✓ Daemon stopped" || echo "⚠ Daemon may still be running"
```

## Phase 14: Verify TypeScript/Go/Rust Extraction (NEW in v1.2.0)

Verify semantic extraction of new language constructs:

```bash
# TypeScript interfaces should be indexed
ember find "Logger" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
ts_results = [r for r in data if r.get('path', '').endswith('.ts')]
print(f'✓ TypeScript Logger results: {len(ts_results)}')
"

# TypeScript type aliases should be indexed
ember find "Handler" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'✓ TypeScript Handler type alias: {len(data)} results')
"

# Go structs should be indexed
ember find "Config" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
go_results = [r for r in data if r.get('path', '').endswith('.go')]
print(f'✓ Go Config struct: {len(go_results)} results')
"

# Rust enums should be indexed
ember find "Status" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
rust_results = [r for r in data if r.get('path', '').endswith('.rs')]
print(f'✓ Rust Status enum: {len(rust_results)} results')
"

# Rust traits should be indexed
ember find "Display" --json | python3 -c "
import sys, json
data = json.load(sys.stdin)
rust_results = [r for r in data if r.get('path', '').endswith('.rs')]
print(f'✓ Rust Display trait: {len(rust_results)} results')
"
```

## Phase 15: Performance Check (Optional)

Quick performance spot-check:

```bash
# Time a sync operation
echo "Timing sync performance..."
time ember sync --reindex

# Time a search operation
echo "Timing search performance..."
time ember find "function class" > /dev/null
```

## Phase 16: Cleanup

```bash
# Go back to original directory
cd /Users/sammcvicker/projects/ember

# Cleanup note
echo ""
echo "Test directories created:"
echo "  - $TEST_DIR"
echo "  - $TEST_DIR_2 (if created)"
echo "  - $TEST_DIR_MODEL (if created)"
echo "  - $TEST_DIR_DIM (if created)"
echo ""
echo "These can be safely deleted with: rm -rf /tmp/ember-*-test-* /tmp/ember-*-$(date +%Y)*"
```

## Important Notes

**What Cannot Be Tested:**
- Progress bars (they use `transient=True` and disappear when complete)
- Interactive TUI (`ember search`) - requires user interaction
- Interactive editor opening (`ember open`, `ember config edit`) - requires user interaction
- Visual styling/colors (output formatting is environment-dependent)
- Actual embedding quality (requires human evaluation)

**What IS Tested:**
- All CLI commands (init, sync, find, cat, open error handling, status, config)
- JSON output parsing and validation
- File creation and database initialization (config.toml, index.db)
- Incremental sync detection
- Search result caching for cat/open
- Path and language filters
- Configuration loading (local and global)
- Error handling for edge cases
- Git integration (commits, staged files, worktree)
- Multiple embedding model support (minilm, jina, bge-small)
- TypeScript semantic extraction (interfaces, type aliases, arrow functions)
- Go semantic extraction (structs, interfaces)
- Rust semantic extraction (structs, enums, traits)
- Daemon start/stop/status
- Dimension mismatch detection on model change

## Success Criteria

A successful test run should show:
- ✓ All commands execute without crashes
- ✓ Init creates required files (config.toml, index.db - NO state.json)
- ✓ Sync correctly indexes files and detects changes
- ✓ Incremental sync detects when no changes exist
- ✓ Find returns relevant results in both text and JSON modes
- ✓ Filters (--in, --lang, -k, PATH argument) work correctly
- ✓ Cat command displays cached results with syntax highlighting
- ✓ Error handling works for invalid inputs
- ✓ Config changes are respected (local and global)
- ✓ Auto-sync triggers when index is stale
- ✓ Status command correctly reports index freshness
- ✓ Config command group works (show, path)
- ✓ TypeScript interfaces, type aliases, and arrow functions are extracted
- ✓ Go structs and interfaces are extracted
- ✓ Rust structs, enums, and traits are extracted
- ✓ Model selection during init works (--model flag)
- ✓ Daemon can be started, queried, and stopped
- ✓ Dimension mismatch is detected when model changes

## Reflection Prompt

After completing all tests, reflect on:
1. **What passed:** List all successful test cases
2. **What failed:** Any commands that errored or produced unexpected output
3. **Performance:** Were sync and search operations reasonably fast?
4. **Edge cases:** Did error handling work as expected?
5. **User experience:** Is the CLI output clear and helpful?
6. **New features:** Do TypeScript/Go/Rust extractions work correctly?
7. **Regression risks:** Any behavior that differs from expected functionality?

Report findings in a structured summary with specific command outputs for any failures.

---

**Remember:** This is a functional test, not a fix session. Document issues but don't modify code unless explicitly asked to fix something.

---

**Last Updated:** 2025-12-24 (Updated for v1.2.0 features)
