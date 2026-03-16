"""Tests for guesty_cli.core.circuit_breaker."""
import time
import threading
import pytest
from unittest.mock import patch
from guesty_cli.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen


class TestCircuitBreakerInitialState:
    """Initial state is 'closed'."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == 'closed'

    def test_initial_failure_count_is_zero(self):
        cb = CircuitBreaker()
        assert cb.failure_count == 0


class TestRecordSuccess:
    """record_success() keeps state closed."""

    def test_success_keeps_closed(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == 'closed'

    def test_success_returns_false_when_not_recovering(self):
        cb = CircuitBreaker()
        result = cb.record_success()
        assert result is False


class TestRecordFailure:
    """record_failure() increments failure count."""

    def test_single_failure_increments_count(self):
        cb = CircuitBreaker()
        cb.record_failure()
        assert cb.failure_count == 1

    def test_multiple_failures_increment(self):
        cb = CircuitBreaker()
        for _ in range(3):
            cb.record_failure()
        assert cb.failure_count == 3

    def test_failure_returns_false_below_threshold(self):
        cb = CircuitBreaker()
        result = cb.record_failure()
        assert result is False


class TestCircuitOpens:
    """5 consecutive failures opens circuit (state = 'open')."""

    def test_five_failures_opens_circuit(self):
        cb = CircuitBreaker()
        for i in range(4):
            result = cb.record_failure()
            assert result is False
        result = cb.record_failure()
        assert result is True
        assert cb.state == 'open'

    def test_check_raises_when_open(self):
        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_failure()
        with pytest.raises(CircuitBreakerOpen):
            cb.check()


class TestCircuitBreakerOpen:
    """CircuitBreakerOpen has retry_after attribute."""

    def test_has_retry_after(self):
        exc = CircuitBreakerOpen(retry_after=15.0)
        assert exc.retry_after == 15.0

    def test_message_contains_retry_info(self):
        exc = CircuitBreakerOpen(retry_after=15.0)
        assert "15" in str(exc)


class TestRecordSuccessAfterOpen:
    """record_success() after open resets to closed."""

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_failure()
        assert cb.state == 'open'
        was_open = cb.record_success()
        assert was_open is True
        assert cb.state == 'closed'
        assert cb.failure_count == 0


class TestHalfOpen:
    """After RESET_TIME expires, state becomes 'half-open' and check() doesn't raise."""

    def test_half_open_after_reset_time(self):
        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_failure()
        assert cb.state == 'open'

        # Simulate time passing beyond RESET_TIME
        with patch('guesty_cli.core.circuit_breaker.time') as mock_time:
            # record_failure used real time.time(), so _last_failure is set
            # For state check, we need time.time() to return a future value
            mock_time.time.return_value = time.time() + cb.RESET_TIME + 1
            assert cb.state == 'half-open'

    def test_check_does_not_raise_when_half_open(self):
        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_failure()

        with patch('guesty_cli.core.circuit_breaker.time') as mock_time:
            mock_time.time.return_value = time.time() + cb.RESET_TIME + 1
            # Should not raise
            cb.check()
            # After check in half-open, state resets to closed
            assert cb.state == 'closed'


class TestThreadSafety:
    """Thread safety: concurrent record_failure() calls don't corrupt state."""

    def test_concurrent_failures(self):
        cb = CircuitBreaker()
        errors = []

        def fail_many():
            try:
                for _ in range(100):
                    cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cb.failure_count == 400
        assert cb.state == 'open'


class TestFailureCountProperty:
    """failure_count property returns correct value."""

    def test_failure_count_after_failures(self):
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 3

    def test_failure_count_resets_on_success(self):
        cb = CircuitBreaker()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
