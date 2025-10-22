"""Daemon lifecycle management (start/stop/status).

Handles spawning, stopping, and monitoring the daemon process.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ember.adapters.daemon.client import is_daemon_running

logger = logging.getLogger(__name__)


class DaemonLifecycle:
    """Daemon lifecycle manager."""

    def __init__(
        self,
        socket_path: Path | None = None,
        pid_file: Path | None = None,
        log_file: Path | None = None,
        idle_timeout: int = 900,
    ):
        """Initialize lifecycle manager.

        Args:
            socket_path: Path to Unix socket (default: ~/.ember/daemon.sock)
            pid_file: Path to PID file (default: ~/.ember/daemon.pid)
            log_file: Path to log file (default: ~/.ember/daemon.log)
            idle_timeout: Daemon idle timeout in seconds
        """
        ember_dir = Path.home() / ".ember"
        self.socket_path = socket_path or (ember_dir / "daemon.sock")
        self.pid_file = pid_file or (ember_dir / "daemon.pid")
        self.log_file = log_file or (ember_dir / "daemon.log")
        self.idle_timeout = idle_timeout

        # Ensure ember directory exists
        ember_dir.mkdir(parents=True, exist_ok=True)

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if daemon is running and healthy
        """
        return is_daemon_running(self.socket_path)

    def get_pid(self) -> int | None:
        """Get daemon PID from PID file.

        Returns:
            PID if file exists and contains valid PID, else None
        """
        if not self.pid_file.exists():
            return None

        try:
            pid_str = self.pid_file.read_text().strip()
            return int(pid_str)
        except (OSError, ValueError):
            return None

    def is_process_alive(self, pid: int) -> bool:
        """Check if a process is alive.

        Args:
            pid: Process ID

        Returns:
            True if process exists
        """
        try:
            # Send signal 0 (no-op, just checks if process exists)
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def cleanup_stale_files(self) -> None:
        """Clean up stale socket and PID files."""
        # Check if PID file exists
        pid = self.get_pid()
        if pid is not None and not self.is_process_alive(pid):
            # Process not alive, remove stale PID file
            logger.info(f"Removing stale PID file (process {pid} not found)")
            self.pid_file.unlink()
            pid = None

        # If no valid PID, remove socket if it exists
        if pid is None and self.socket_path.exists():
            logger.info(f"Removing stale socket: {self.socket_path}")
            self.socket_path.unlink()

    def start(self, foreground: bool = False) -> bool:
        """Start the daemon.

        Args:
            foreground: Run in foreground (for debugging)

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If start fails
        """
        # Check if already running
        if self.is_running():
            logger.info("Daemon already running")
            return True

        # Clean up stale files
        self.cleanup_stale_files()

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "ember.adapters.daemon.server",
            "--socket",
            str(self.socket_path),
            "--idle-timeout",
            str(self.idle_timeout),
            "--log-level",
            "INFO",
        ]

        try:
            if foreground:
                # Run in foreground (blocks)
                logger.info("Starting daemon in foreground...")
                subprocess.run(cmd, check=True)
                return True
            else:
                # Run in background (detached)
                logger.info("Starting daemon in background...")

                # Spawn detached process - capture stderr initially for debugging
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,  # Capture stderr to report startup failures
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # Detach from parent
                )

                # Check if process died instantly (before writing PID file)
                time.sleep(0.1)  # Brief wait for instant failures
                exit_code = process.poll()
                if exit_code is not None:
                    # Process already exited - try to get stderr
                    stderr_output = ""
                    try:
                        stderr_bytes = process.stderr.read() if process.stderr else b""
                        stderr_output = stderr_bytes.decode("utf-8", errors="replace").strip()
                    except Exception:
                        pass

                    error_msg = f"Daemon failed to start (exit code: {exit_code})"
                    if stderr_output:
                        error_msg += f"\nStderr: {stderr_output}"
                    error_msg += f"\nCheck daemon logs at: {self.log_file}"
                    raise RuntimeError(error_msg)

                # Close stderr now that we've confirmed startup
                if process.stderr:
                    process.stderr.close()

                # NOW write PID file (process survived initial check)
                self.pid_file.write_text(str(process.pid))
                logger.info(f"Daemon started with PID {process.pid}")

                # Wait for daemon to be ready (up to 20 seconds to allow model loading)
                # Model loading typically takes 3-5 seconds, but can be longer on first download
                for i in range(40):  # 40 * 0.5s = 20s
                    time.sleep(0.5)
                    if self.is_running():
                        elapsed = (i + 1) * 0.5
                        logger.info(f"Daemon is ready (took {elapsed:.1f}s)")
                        return True

                # Daemon started but health check timed out
                # Check if process is still alive
                if self.is_process_alive(process.pid):
                    # Clean up PID file for failed startup
                    self.pid_file.unlink(missing_ok=True)
                    raise RuntimeError(
                        "Daemon process started but not responding to health checks after 20s. "
                        "This may indicate model loading issues. Check daemon logs at: "
                        f"{self.log_file}"
                    )
                else:
                    # Clean up PID file for failed startup
                    self.pid_file.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Daemon process {process.pid} exited unexpectedly during startup. "
                        f"Check daemon logs at: {self.log_file}"
                    )

        except Exception as e:
            raise RuntimeError(f"Failed to start daemon: {e}") from e

    def stop(self, timeout: int = 10) -> bool:
        """Stop the daemon gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped successfully
        """
        # Get PID
        pid = self.get_pid()
        if pid is None:
            logger.info("Daemon not running (no PID file)")
            self.cleanup_stale_files()
            return True

        # Check if process exists
        if not self.is_process_alive(pid):
            logger.info(f"Daemon not running (process {pid} not found)")
            self.cleanup_stale_files()
            return True

        # Try SIGTERM first for graceful shutdown
        logger.info(f"Stopping daemon (PID {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            # SIGTERM failed - check if process already dead or no permission
            if not self.is_process_alive(pid):
                logger.info("Process already dead")
                self.cleanup_stale_files()
                return True
            logger.warning(f"SIGTERM failed: {e}, trying SIGKILL...")
            # Don't return here! Fall through to SIGKILL
        else:
            # SIGTERM succeeded, wait for graceful shutdown
            for _ in range(timeout * 2):  # Check every 0.5s
                time.sleep(0.5)
                if not self.is_process_alive(pid):
                    logger.info("Daemon stopped gracefully")
                    self.cleanup_stale_files()
                    return True

        # Still alive after SIGTERM - force kill
        logger.warning("Daemon did not stop gracefully, sending SIGKILL...")
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as e:
            # SIGKILL failed - check if process died between check and kill
            if not self.is_process_alive(pid):
                logger.info("Process died before SIGKILL")
                self.cleanup_stale_files()
                return True
            logger.error(f"Failed to kill daemon: {e}")
            return False

        # Verify SIGKILL worked before cleanup
        time.sleep(0.5)
        if not self.is_process_alive(pid):
            logger.info("Daemon force-killed")
            self.cleanup_stale_files()
            return True
        else:
            logger.error("Daemon survived SIGKILL! Manual cleanup required.")
            return False

    def restart(self, foreground: bool = False) -> bool:
        """Restart the daemon.

        Args:
            foreground: Run in foreground (for debugging)

        Returns:
            True if restarted successfully
        """
        logger.info("Restarting daemon...")
        self.stop()
        return self.start(foreground=foreground)

    def status(self) -> dict:
        """Get daemon status.

        Returns:
            Dictionary with status information
        """
        is_running = self.is_running()
        pid = self.get_pid()

        status = {
            "running": is_running,
            "pid": pid,
            "socket": str(self.socket_path),
            "socket_exists": self.socket_path.exists(),
            "pid_file": str(self.pid_file),
            "pid_file_exists": self.pid_file.exists(),
            "log_file": str(self.log_file),
        }

        # Check for stale files
        if not is_running:
            if pid is not None and self.is_process_alive(pid):
                status["status"] = "unresponsive"
                status["message"] = f"Process {pid} exists but not responding"
            elif self.socket_path.exists() or self.pid_file.exists():
                status["status"] = "stale"
                status["message"] = "Stale files found (daemon not running)"
            else:
                status["status"] = "stopped"
                status["message"] = "Daemon is not running"
        else:
            status["status"] = "running"
            status["message"] = f"Daemon is running (PID {pid})"

        return status

    def ensure_running(self, wait: bool = True) -> bool:
        """Ensure daemon is running, start if needed.

        This is the key method used by CLI commands to auto-start the daemon.

        Args:
            wait: Wait for daemon to be ready

        Returns:
            True if daemon is running
        """
        if self.is_running():
            return True

        logger.info("Daemon not running, starting...")
        try:
            return self.start(foreground=False)
        except RuntimeError as e:
            logger.error(f"Failed to start daemon: {e}")
            return False
