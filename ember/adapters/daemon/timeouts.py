"""Centralized timeout configuration for daemon operations.

All daemon-related timeout values are defined here to:
1. Provide a single source of truth for tuning
2. Document the purpose of each timeout value
3. Enable easy adjustment for different environments (e.g., slower systems)
"""


class DaemonTimeouts:
    """Centralized timeout configuration for daemon operations.

    All values are in seconds unless otherwise noted.

    Groups:
        SOCKET_*: Client socket operation timeouts
        READY_*: Waiting for daemon to become ready after startup
        SIGTERM_*: Graceful shutdown timeouts
        SIGKILL_*: Force kill timeouts
        SERVER_*: Server-side timeouts
        HEALTH_*: Health check timeouts
    """

    # =========================================================================
    # Socket Operation Timeouts
    # =========================================================================

    SOCKET_OPERATION: float = 5.0
    """Timeout for client socket operations (connect, send, receive).

    This value should be long enough to handle:
    - Initial connection establishment
    - Large batch embedding requests
    - Network/IPC latency on loaded systems

    If embeddings are timing out, consider increasing this value.
    """

    # =========================================================================
    # Daemon Ready Wait Timeouts
    # =========================================================================

    READY_WAIT_DEFAULT: float = 30.0
    """Default timeout for cached models without specific timing data.

    Used for unknown models or when model name isn't available.
    Provides a reasonable margin for most embedding models.
    """

    # Model-specific load times based on real-world measurements (#385)
    # These times include model file loading, PyTorch initialization,
    # and first tensor operations on Apple Silicon (M1/M2/M3).
    MODEL_LOAD_TIMES: dict[str, float] = {
        # Jina is 1.6GB with trust_remote_code - loading takes 15-25s on Apple Silicon
        "jinaai/jina-embeddings-v2-base-code": 45.0,
        # MiniLM is ~100MB - fast loading
        "sentence-transformers/all-MiniLM-L6-v2": 20.0,
        # BGE-small is ~130MB - fast loading
        "BAAI/bge-small-en-v1.5": 20.0,
    }
    """Model-specific startup timeouts for cached models.

    Different models have different load times based on:
    - Model size (file I/O time)
    - Architecture complexity (initialization time)
    - Whether trust_remote_code is needed (additional setup)
    - Hardware (Apple Silicon MPS vs CUDA vs CPU)

    The Jina model in particular needs extra time because:
    - It's 1.6GB vs ~100-130MB for other models
    - It uses trust_remote_code which adds initialization overhead
    - Apple Silicon MPS backend initialization can be slow on first use

    These values include buffer time for socket creation and health checks.
    """

    READY_WAIT_FIRST_RUN: float = 120.0
    """Maximum time to wait when model needs to be downloaded.

    On first run (or if model cache is cleared), the embedding model must be
    downloaded from HuggingFace. This can take significant time:
    - Jina model (~1.6GB): 30-120s depending on network
    - MiniLM (~100MB): 5-30s
    - BGE-small (~130MB): 5-30s

    This longer timeout prevents startup failures on fresh installs.
    Once cached, subsequent startups use model-specific timeouts.
    """

    READY_CHECK_INTERVAL: float = 0.5
    """Interval between health checks when waiting for daemon ready.

    Controls how frequently we poll the daemon during startup.
    Lower values detect readiness faster but consume more CPU.
    0.5s provides a good balance between responsiveness and efficiency.
    """

    # =========================================================================
    # Graceful Shutdown (SIGTERM) Timeouts
    # =========================================================================

    SIGTERM_WAIT: int = 10
    """Time to wait for graceful shutdown after SIGTERM.

    Gives the daemon time to:
    - Finish any in-progress embedding requests
    - Clean up resources (release model, close socket)
    - Write any final logs

    If the daemon doesn't stop within this time, SIGKILL is sent.
    """

    # =========================================================================
    # Force Kill (SIGKILL) Timeouts
    # =========================================================================

    SIGKILL_WAIT: float = 2.5
    """Time to wait after sending SIGKILL.

    SIGKILL cannot be caught or ignored, so this is primarily to allow
    the OS to clean up the process. In practice, death should be nearly
    instant. If a process survives SIGKILL, something is seriously wrong
    (kernel issue, zombie, etc.).
    """

    DEATH_CHECK_INTERVAL: float = 0.5
    """Interval between checks when waiting for process death.

    Used when waiting for a process to die after SIGTERM or SIGKILL.
    0.5s provides reasonable responsiveness without excessive polling.
    """

    # =========================================================================
    # Server-Side Timeouts
    # =========================================================================

    SERVER_ACCEPT: float = 1.0
    """Timeout for server accept() calls.

    The server uses non-blocking accept with this timeout to allow
    periodic checks for:
    - Idle timeout (auto-shutdown when inactive)
    - Shutdown signals (SIGTERM/SIGINT)

    Lower values make the server more responsive to shutdown but
    increase CPU usage due to more frequent wakeups.
    """

    # =========================================================================
    # Health Check Timeouts
    # =========================================================================

    HEALTH_CHECK: float = 2.0
    """Timeout for daemon health check requests.

    Used by is_daemon_running() and get_daemon_pid() to verify
    the daemon is responsive. This is shorter than SOCKET_OPERATION
    because health checks should be fast (no model inference).

    If health checks are timing out on a busy system, this may need
    to be increased, but first check if the daemon is overloaded.
    """

    # =========================================================================
    # Startup Failure Detection
    # =========================================================================

    STARTUP_FAILURE_LOOP_WAIT: float = 0.1
    """Interval for cleanup loop when terminating unresponsive startup.

    When a daemon starts but doesn't become responsive within READY_WAIT,
    we try to terminate it gracefully. This controls how long we wait
    between checks (10 iterations = 1.0s total).
    """

    STARTUP_FAILURE_LOOP_COUNT: int = 10
    """Number of iterations for startup failure cleanup loop.

    Combined with STARTUP_FAILURE_LOOP_WAIT, this defines the total
    time spent trying to gracefully terminate an unresponsive daemon
    before falling back to SIGKILL.
    """

    @classmethod
    def get_model_timeout(cls, model_id: str | None) -> float:
        """Get the startup timeout for a specific model.

        Args:
            model_id: The canonical HuggingFace model ID, or None.

        Returns:
            Model-specific timeout if known, otherwise READY_WAIT_DEFAULT.
        """
        if model_id is None:
            return cls.READY_WAIT_DEFAULT
        return cls.MODEL_LOAD_TIMES.get(model_id, cls.READY_WAIT_DEFAULT)
