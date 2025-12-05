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

from ember.adapters.daemon.client import get_daemon_pid, is_daemon_running

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
            True if process exists and is not a zombie
        """
        try:
            # First try to collect any zombie children to avoid false positives
            # This handles the case where we spawned a daemon that has exited
            # but hasn't been reaped yet (zombie state)
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                # Process is not our child, that's fine
                pass
            except OSError:
                # Process doesn't exist or other error
                pass

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

    def _cleanup_failed_startup(self) -> None:
        """Clean up PID file after a failed startup attempt."""
        self.pid_file.unlink(missing_ok=True)

    def _wait_for_daemon_ready(self, max_wait_secs: float = 20.0) -> bool:
        """Wait for daemon to become ready.

        Args:
            max_wait_secs: Maximum seconds to wait for daemon to be ready

        Returns:
            True if daemon is ready, False if timeout
        """
        check_interval = 0.5
        num_checks = int(max_wait_secs / check_interval)

        for i in range(num_checks):
            time.sleep(check_interval)
            if self.is_running():
                elapsed = (i + 1) * check_interval
                logger.info(f"Daemon is ready (took {elapsed:.1f}s)")
                return True

        return False

    def _read_stderr_output(self, process: subprocess.Popen) -> str:
        """Read stderr output from a process for error reporting.

        Args:
            process: The subprocess to read stderr from

        Returns:
            Decoded stderr output, or empty string if unavailable
        """
        if not process.stderr:
            return ""
        try:
            stderr_bytes = process.stderr.read()
            return stderr_bytes.decode("utf-8", errors="replace").strip()
        except Exception:
            logger.debug("Failed to read stderr from process")
            return ""

    def _start_foreground(self, cmd: list[str]) -> bool:
        """Start daemon in foreground mode (blocking).

        Args:
            cmd: Command to execute

        Returns:
            True if started successfully
        """
        logger.info("Starting daemon in foreground...")
        subprocess.run(cmd, check=True)
        return True

    def _spawn_background_process(self, cmd: list[str]) -> subprocess.Popen:
        """Spawn daemon as a background process.

        Args:
            cmd: Command to execute

        Returns:
            The spawned process
        """
        logger.info("Starting daemon in background...")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,  # Capture stderr to report startup failures
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent
        )

    def _write_pid_file(self, process: subprocess.Popen) -> None:
        """Write PID file for the spawned process.

        Args:
            process: The spawned process

        Raises:
            RuntimeError: If PID file cannot be written
        """
        try:
            self.pid_file.write_text(str(process.pid))
            logger.info(f"Daemon started with PID {process.pid}")
        except Exception as e:
            # Failed to write PID file - terminate process to avoid orphan
            process.terminate()
            raise RuntimeError(f"Failed to write PID file: {e}") from e

    def _check_instant_failure(self, process: subprocess.Popen) -> None:
        """Check if the process failed immediately after spawn.

        Args:
            process: The spawned process

        Raises:
            RuntimeError: If process exited immediately with an error
        """
        time.sleep(0.1)  # Brief wait for instant failures
        exit_code = process.poll()
        if exit_code is not None:
            self._cleanup_failed_startup()
            stderr_output = self._read_stderr_output(process)

            error_msg = f"Daemon failed to start (exit code: {exit_code})"
            if stderr_output:
                error_msg += f"\nStderr: {stderr_output}"
            error_msg += f"\nCheck daemon logs at: {self.log_file}"
            raise RuntimeError(error_msg)

    def _handle_startup_timeout(self, process: subprocess.Popen) -> None:
        """Handle the case where daemon didn't become ready in time.

        Args:
            process: The spawned process

        Raises:
            RuntimeError: With appropriate message based on process state
        """
        if self.is_process_alive(process.pid):
            # Process is alive but not responding - terminate it to avoid orphan
            # This prevents the race condition where:
            # 1. We delete the PID file
            # 2. Process eventually becomes ready
            # 3. Status shows "running (PID None)" because no PID file
            logger.warning(
                f"Daemon process {process.pid} not responding after 20s, terminating..."
            )
            try:
                os.kill(process.pid, signal.SIGTERM)
                # Give process brief time to exit gracefully
                for _ in range(10):  # Up to 1 second
                    time.sleep(0.1)
                    if not self.is_process_alive(process.pid):
                        break
                else:
                    # Force kill if still alive
                    os.kill(process.pid, signal.SIGKILL)
            except OSError:
                pass  # Process already dead

            self._cleanup_failed_startup()
            raise RuntimeError(
                "Daemon process started but not responding to health checks after 20s. "
                "Process was terminated. This may indicate model loading issues. "
                f"Check daemon logs at: {self.log_file}"
            )
        else:
            self._cleanup_failed_startup()
            raise RuntimeError(
                f"Daemon process {process.pid} exited unexpectedly during startup. "
                f"Check daemon logs at: {self.log_file}"
            )

    def start(self, foreground: bool = False) -> bool:
        """Start the daemon.

        Args:
            foreground: Run in foreground (for debugging)

        Returns:
            True if started successfully

        Raises:
            RuntimeError: If start fails
        """
        if self.is_running():
            logger.info("Daemon already running")
            return True

        self.cleanup_stale_files()

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
                return self._start_foreground(cmd)

            process = self._spawn_background_process(cmd)
            self._write_pid_file(process)

            try:
                self._check_instant_failure(process)
            finally:
                if process.stderr:
                    process.stderr.close()

            if self._wait_for_daemon_ready():
                return True

            self._handle_startup_timeout(process)

        except Exception as e:
            raise RuntimeError(f"Failed to start daemon: {e}") from e

        # This return is unreachable but satisfies type checker
        return False

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
        # Give process time to fully terminate (may take longer on some systems)
        for _ in range(5):  # Up to 2.5s total
            time.sleep(0.5)
            if not self.is_process_alive(pid):
                logger.info("Daemon force-killed")
                self.cleanup_stale_files()
                return True

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

        # If daemon is running but PID file is missing, try to recover PID
        # from daemon health check (#214)
        if is_running and pid is None:
            pid = get_daemon_pid(self.socket_path)

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
            # Never show "PID None" - use "unknown" if PID couldn't be recovered (#214)
            if pid is not None:
                status["message"] = f"Daemon is running (PID {pid})"
            else:
                status["message"] = "Daemon is running (PID unknown)"

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
