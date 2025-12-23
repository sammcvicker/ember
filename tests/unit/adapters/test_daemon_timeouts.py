"""Unit tests for daemon timeout configuration."""

from ember.adapters.daemon.timeouts import DaemonTimeouts


class TestDaemonTimeoutsValues:
    """Tests for DaemonTimeouts configuration values."""

    def test_socket_operation_timeout_is_positive(self) -> None:
        """Socket operation timeout must be positive."""
        assert DaemonTimeouts.SOCKET_OPERATION > 0

    def test_ready_wait_timeout_is_positive(self) -> None:
        """Ready wait timeout must be positive."""
        assert DaemonTimeouts.READY_WAIT > 0

    def test_ready_check_interval_is_positive(self) -> None:
        """Ready check interval must be positive."""
        assert DaemonTimeouts.READY_CHECK_INTERVAL > 0

    def test_ready_check_interval_less_than_ready_wait(self) -> None:
        """Check interval should be less than total wait time."""
        assert DaemonTimeouts.READY_CHECK_INTERVAL < DaemonTimeouts.READY_WAIT

    def test_sigterm_wait_is_positive(self) -> None:
        """SIGTERM wait timeout must be positive."""
        assert DaemonTimeouts.SIGTERM_WAIT > 0

    def test_sigkill_wait_is_positive(self) -> None:
        """SIGKILL wait timeout must be positive."""
        assert DaemonTimeouts.SIGKILL_WAIT > 0

    def test_death_check_interval_is_positive(self) -> None:
        """Death check interval must be positive."""
        assert DaemonTimeouts.DEATH_CHECK_INTERVAL > 0

    def test_server_accept_timeout_is_positive(self) -> None:
        """Server accept timeout must be positive."""
        assert DaemonTimeouts.SERVER_ACCEPT > 0

    def test_health_check_timeout_is_positive(self) -> None:
        """Health check timeout must be positive."""
        assert DaemonTimeouts.HEALTH_CHECK > 0

    def test_health_check_shorter_than_socket_operation(self) -> None:
        """Health checks should be quicker than general socket ops."""
        # Health checks don't involve model inference, so should be faster
        assert DaemonTimeouts.HEALTH_CHECK <= DaemonTimeouts.SOCKET_OPERATION

    def test_startup_failure_loop_values_are_positive(self) -> None:
        """Startup failure loop values must be positive."""
        assert DaemonTimeouts.STARTUP_FAILURE_LOOP_WAIT > 0
        assert DaemonTimeouts.STARTUP_FAILURE_LOOP_COUNT > 0


class TestDaemonTimeoutsDocumentation:
    """Tests to verify timeout values are documented."""

    def test_class_has_substantial_documentation(self) -> None:
        """DaemonTimeouts class should have substantial documentation."""
        class_doc = DaemonTimeouts.__doc__
        assert class_doc is not None
        # Verify the class has substantial documentation
        assert len(class_doc) > 100

    def test_timeout_values_are_class_attributes(self) -> None:
        """Timeout values should be accessible as class attributes."""
        expected_timeouts = [
            "SOCKET_OPERATION",
            "READY_WAIT",
            "READY_CHECK_INTERVAL",
            "SIGTERM_WAIT",
            "SIGKILL_WAIT",
            "DEATH_CHECK_INTERVAL",
            "SERVER_ACCEPT",
            "HEALTH_CHECK",
            "STARTUP_FAILURE_LOOP_WAIT",
            "STARTUP_FAILURE_LOOP_COUNT",
        ]
        for attr in expected_timeouts:
            assert hasattr(DaemonTimeouts, attr), f"Missing timeout: {attr}"
            value = getattr(DaemonTimeouts, attr)
            assert isinstance(value, (int, float)), f"{attr} should be numeric"
