"""Circuit breaker for Guesty API calls.

Prevents hammering the API when it's consistently failing.
After THRESHOLD consecutive failures, the circuit opens and blocks
requests for RESET_TIME seconds before allowing a retry.
"""
import threading
import time


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open."""
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open. Retry after {retry_after:.0f}s")


class CircuitBreaker:
    """Thread-safe circuit breaker."""

    THRESHOLD = 5        # Consecutive failures to open circuit
    RESET_TIME = 30.0    # Seconds before attempting reset

    def __init__(self):
        self._lock = threading.Lock()
        self._failures = 0
        self._last_failure = 0.0
        self._open = False

    def check(self):
        """Check if the circuit is open. Raises CircuitBreakerOpen if so."""
        with self._lock:
            if not self._open:
                return

            elapsed = time.time() - self._last_failure
            if elapsed > self.RESET_TIME:
                # Half-open: allow one attempt
                self._open = False
                self._failures = 0
                return

            raise CircuitBreakerOpen(self.RESET_TIME - elapsed)

    def record_success(self):
        """Record a successful request."""
        with self._lock:
            was_open = self._open
            self._failures = 0
            self._open = False
            return was_open  # True if we just recovered

    def record_failure(self):
        """Record a failed request. Returns True if circuit just opened."""
        with self._lock:
            self._failures += 1
            self._last_failure = time.time()

            if self._failures >= self.THRESHOLD:
                self._open = True
                return True
            return False

    @property
    def state(self):
        """Current state: 'closed', 'open', or 'half-open'."""
        with self._lock:
            if not self._open:
                return 'closed'
            elapsed = time.time() - self._last_failure
            if elapsed > self.RESET_TIME:
                return 'half-open'
            return 'open'

    @property
    def failure_count(self):
        with self._lock:
            return self._failures
