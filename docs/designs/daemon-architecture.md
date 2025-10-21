# Daemon Architecture for Model Loading (Issue #46)

**Status:** Design Phase
**Date:** 2025-10-21
**Milestone:** v1.0.0

---

## Problem Statement

Model loading takes ~2.9 seconds on every `ember find` command due to:
- `sentence_transformers` import: 2,304ms
- Model weight loading: 557ms

This happens on every CLI invocation (fresh Python process each time).

**Target:** <500ms total (ideal: <200ms)

---

## Solution: Persistent Model Server (Daemon)

Keep the embedding model loaded in a long-running background process. CLI commands communicate with the daemon via IPC for instant embeddings.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│  CLI Command (ember find / ember sync)                  │
│                                                          │
│  1. Creates EmbedderClient (adapter)                    │
│  2. Checks if daemon is running                         │
│  3. Connects via Unix socket                            │
│  4. Sends embed request                                 │
│  5. Receives embeddings                                 │
└────────────────┬────────────────────────────────────────┘
                 │ IPC via Unix Socket
                 │ JSON-RPC protocol
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Daemon Process (ember-daemon)                          │
│                                                          │
│  - Loads model on startup (~3 seconds once)            │
│  - Listens on Unix socket                               │
│  - Handles embed_texts requests                         │
│  - Returns embeddings                                   │
│  - Auto-shuts down after idle timeout (15 min)         │
└─────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### 1. IPC Mechanism: Unix Domain Sockets

**Choice:** Unix domain sockets

**Rationale:**
- ✅ Fastest IPC on Unix systems (lower overhead than TCP)
- ✅ Bidirectional communication
- ✅ Simple, well-supported in Python (`socket` stdlib)
- ✅ Works on macOS and Linux
- ✅ File-based addressing (easy to check if daemon is running)

**Alternatives Considered:**
- Named pipes: Unidirectional, more complex bidirectional setup
- HTTP/REST: Higher overhead, overkill for local IPC
- multiprocessing.Queue: Doesn't survive across separate processes
- ZeroMQ: Extra dependency

**Socket Location:** `~/.ember/daemon.sock` (global, not per-repo)

---

### 2. Communication Protocol: Simple JSON-RPC

**Request Format:**
```json
{
  "method": "embed_texts",
  "params": {
    "texts": ["def foo():", "class Bar:"]
  },
  "id": 1
}
```

**Response Format:**
```json
{
  "result": [[0.1, 0.2, ...], [0.3, 0.4, ...]],
  "error": null,
  "id": 1
}
```

**Error Response:**
```json
{
  "result": null,
  "error": {"code": 500, "message": "Model not loaded"},
  "id": 1
}
```

**Rationale:**
- Simple, human-readable for debugging
- JSON is stdlib, no extra dependencies
- Allows future extensibility (health checks, model info, etc.)

**Protocol Details:**
- Messages are newline-delimited JSON
- Each message is a complete JSON object followed by `\n`
- Client sends request, waits for response
- Synchronous request/response (no async needed for v1.0)

---

### 3. Daemon Scope: Global (Not Per-Repo)

**Choice:** One global daemon for all repos

**Rationale:**
- ✅ Simpler: one daemon process, one socket
- ✅ Lower resource usage: one model in memory (~161MB)
- ✅ Model is same for all repos (Jina Code model is universal)
- ✅ No repo-specific configuration needed

**Alternatives Considered:**
- Per-repo daemon: Complex (multiple daemons, coordination), wasteful (multiple models)

**Socket Path:** `~/.ember/daemon.sock` (user-level, not per-repo)
**PID File:** `~/.ember/daemon.pid`

---

### 4. Lifecycle Management

#### Auto-Start
- On `ember find` or `ember sync`, check if daemon is running
- If not running: spawn daemon in background, wait for ready
- Client retries connection for up to 5 seconds (allows daemon startup time)

#### Auto-Stop
- Daemon tracks last request time
- If idle for 15 minutes (configurable), daemon shuts down gracefully
- Cleans up socket and PID file on exit

#### Manual Management
New commands:
- `ember daemon start` - Start daemon manually
- `ember daemon stop` - Stop daemon gracefully
- `ember daemon status` - Check if running, show stats (uptime, requests served)
- `ember daemon restart` - Stop and start

#### Robustness
- Daemon creates PID file on start, removes on clean exit
- Client checks PID file before connecting
- If socket exists but daemon is dead (stale socket): remove socket, start new daemon
- If daemon crashes mid-request: client catches exception, falls back to direct mode (one time)

---

### 5. Fallback Strategy

**Graceful Degradation:**
- If daemon fails to start after retries: fall back to direct mode (current JinaCodeEmbedder)
- Log warning but don't fail the command
- User sees slower performance but command succeeds

**Implementation:**
```python
class EmbedderClient(Embedder):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._daemon_embed(texts)
        except DaemonError:
            logger.warning("Daemon failed, falling back to direct mode")
            return self._direct_embed(texts)
```

**Direct Mode:**
- Config option: `model.mode = "direct"` disables daemon entirely
- Useful for debugging, CI/CD environments

---

### 6. Configuration

**New config section in `.ember/config.toml`:**
```toml
[model]
# Mode: "daemon" (default) or "direct"
mode = "daemon"

# Daemon idle timeout in seconds (default: 900 = 15 minutes)
daemon_timeout = 900

# Max time to wait for daemon startup (default: 5 seconds)
daemon_startup_timeout = 5
```

**Defaults:**
- `mode = "daemon"` (use daemon by default)
- `daemon_timeout = 900` (15 minutes)
- `daemon_startup_timeout = 5` (5 seconds)

---

## Implementation Plan

### Phase 1: Core Daemon Server
**File:** `ember/adapters/daemon/server.py`
- [ ] Implement daemon server process
- [ ] Load model on startup
- [ ] Listen on Unix socket
- [ ] Handle `embed_texts` requests
- [ ] Return embeddings as JSON
- [ ] Implement idle timeout

### Phase 2: Client Adapter
**File:** `ember/adapters/daemon/client.py`
- [ ] Implement `EmbedderClient` (implements `Embedder` protocol)
- [ ] Connect to daemon via Unix socket
- [ ] Send requests, receive responses
- [ ] Handle connection errors
- [ ] Fallback to direct mode on failure

### Phase 3: Lifecycle Management
**File:** `ember/adapters/daemon/lifecycle.py`
- [ ] Auto-start daemon if not running
- [ ] Check if daemon is alive (socket + PID file)
- [ ] Spawn daemon process in background
- [ ] Clean up stale sockets/PIDs
- [ ] Graceful shutdown

### Phase 4: CLI Integration
**File:** `ember/entrypoints/cli.py`
- [ ] Add `ember daemon` subcommand group
- [ ] Commands: `start`, `stop`, `status`, `restart`
- [ ] Update `_create_embedder()` to use `EmbedderClient` by default
- [ ] Respect `model.mode` config

### Phase 5: Configuration
**File:** `ember/adapters/config/config_loader.py`
- [ ] Add `model` section to config schema
- [ ] Load daemon settings from config
- [ ] Provide sensible defaults

### Phase 6: Testing
**Files:** `tests/integration/test_daemon.py`
- [ ] Test daemon start/stop
- [ ] Test embedding via daemon
- [ ] Test fallback to direct mode
- [ ] Test stale socket handling
- [ ] Test idle timeout

---

## Success Criteria

### Performance
- [x] Baseline measured: ~2,900ms current
- [ ] First command after boot: <1,000ms (acceptable, rare)
- [ ] Subsequent commands: <200ms (ideal UX)
- [ ] Daemon startup: <5 seconds (one-time cost)

### Reliability
- [ ] Daemon auto-starts transparently
- [ ] Graceful fallback on daemon failure
- [ ] Clean shutdown (no orphaned processes)
- [ ] Handles stale sockets/PIDs

### Usability
- [ ] Zero configuration for default use case
- [ ] Manual daemon management available
- [ ] Clear status reporting
- [ ] Works on macOS and Linux

---

## File Structure

```
ember/
  adapters/
    daemon/
      __init__.py
      server.py        # Daemon server implementation
      client.py        # Client adapter (Embedder protocol)
      lifecycle.py     # Start/stop/status management
      protocol.py      # JSON-RPC helpers
  entrypoints/
    cli.py             # Add 'daemon' subcommand
tests/
  integration/
    test_daemon.py     # Integration tests
```

---

## Out of Scope (Future v1.1+)

- Model quantization
- GPU acceleration
- Multiple model support
- Remote daemon (network)
- Per-repo daemon option
- Daemon pooling (multiple models)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Daemon crashes | Fallback to direct mode, auto-restart |
| Stale socket/PID | Check PID liveness, clean up stale files |
| Port conflicts | Unix socket (file-based, no ports) |
| Orphaned processes | PID tracking, clean shutdown |
| Windows support | Document as Unix-only (macOS/Linux) for v1.0 |

---

## Timeline Estimate

- Phase 1 (Server): 3 hours
- Phase 2 (Client): 2 hours
- Phase 3 (Lifecycle): 2 hours
- Phase 4 (CLI): 1 hour
- Phase 5 (Config): 1 hour
- Phase 6 (Testing): 3 hours

**Total: ~12 hours**

---

## References

- Issue #46: https://github.com/sammcvicker/ember/issues/46
- Profiling results: `profile_model_loading.py`
- Similar architecture: Language Server Protocol (LSP)
- Python socket docs: https://docs.python.org/3/library/socket.html
