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

                # Spawn detached process
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # Detach from parent
                )

                # Write PID file
                self.pid_file.write_text(str(process.pid))
                logger.info(f"Daemon started with PID {process.pid}")

                # Wait for daemon to be ready (up to 10 seconds)
                for _ in range(20):
                    time.sleep(0.5)
                    if self.is_running():
                        logger.info("Daemon is ready")
                        return True

                raise RuntimeError("Daemon started but not responding")

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

        # Send SIGTERM for graceful shutdown
        logger.info(f"Stopping daemon (PID {pid})...")
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            logger.error(f"Failed to send SIGTERM: {e}")
            return False

        # Wait for process to exit
        for _ in range(timeout * 2):  # Check every 0.5s
            time.sleep(0.5)
            if not self.is_process_alive(pid):
                logger.info("Daemon stopped gracefully")
                self.cleanup_stale_files()
                return True

        # Force kill if still alive
        logger.warning("Daemon did not stop gracefully, sending SIGKILL...")
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
            self.cleanup_stale_files()
            return True
        except OSError as e:
            logger.error(f"Failed to kill daemon: {e}")
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
