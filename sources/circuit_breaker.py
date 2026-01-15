"""
Circuit Breaker Pattern for Manga Source Connectors.

Implements the classic circuit breaker pattern with three states:
- CLOSED: Normal operation, requests pass through
- OPEN: Source has failed repeatedly, all requests fail immediately
- HALF_OPEN: Testing if source has recovered, allow single request

This prevents cascading failures when a source goes down and reduces
unnecessary load on failing services.

Usage:
    breaker = CircuitBreaker("mangadex", failure_threshold=5, recovery_timeout=60)

    if breaker.can_execute():
        try:
            result = source.search(query)
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
    else:
        raise CircuitOpenError(f"Circuit open for {breaker.name}")
"""

import time
import threading
from enum import Enum
from typing import Dict, Optional, Any, Callable
from dataclasses import dataclass, field


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject all requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitOpenError(Exception):
    """Raised when circuit is open and request is rejected."""
    def __init__(self, source_id: str, retry_after: float):
        self.source_id = source_id
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open for '{source_id}', retry after {retry_after:.1f}s")


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5      # Failures before opening circuit
    success_threshold: int = 2      # Successes in half-open to close
    recovery_timeout: float = 60.0  # Seconds before trying half-open
    half_open_max_calls: int = 3    # Max concurrent calls in half-open


@dataclass
class CircuitStats:
    """Statistics for a circuit breaker."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0  # Rejected due to open circuit
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    state_changes: int = 0
    time_in_open: float = 0.0


class CircuitBreaker:
    """
    Circuit breaker for a single source.

    State transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: After any failure
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = threading.Lock()
        self._opened_at: float = 0.0
        self._half_open_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """Get current state, automatically transitioning OPEN -> HALF_OPEN if timeout passed."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._opened_at >= self.config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def stats(self) -> CircuitStats:
        """Get circuit breaker statistics."""
        return self._stats

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self.state == CircuitState.OPEN

    @property
    def retry_after(self) -> float:
        """Seconds until circuit might transition to half-open."""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self._opened_at
        return max(0.0, self.config.recovery_timeout - elapsed)

    def can_execute(self) -> bool:
        """
        Check if a request can be executed.

        Returns True if:
        - Circuit is CLOSED
        - Circuit is HALF_OPEN and under max concurrent calls

        Automatically transitions OPEN -> HALF_OPEN if timeout passed.
        """
        state = self.state  # This may trigger OPEN -> HALF_OPEN transition

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
            return False

        # OPEN state
        return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._stats.total_requests += 1
            self._stats.successful_requests += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls = max(0, self._half_open_calls - 1)
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._stats.total_requests += 1
            self._stats.failed_requests += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens circuit
                self._half_open_calls = 0
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def record_rejection(self) -> None:
        """Record a rejected request (circuit open)."""
        with self._lock:
            self._stats.rejected_requests += 1

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state (must hold lock)."""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._stats.state_changes += 1

        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._stats.consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            if old_state == CircuitState.OPEN:
                self._stats.time_in_open += time.time() - self._opened_at
        elif new_state == CircuitState.CLOSED:
            self._stats.consecutive_failures = 0
            if old_state == CircuitState.OPEN:
                self._stats.time_in_open += time.time() - self._opened_at

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._stats = CircuitStats()
            self._opened_at = 0.0
            self._half_open_calls = 0

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status as dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "is_closed": self.is_closed,
            "retry_after": round(self.retry_after, 1),
            "stats": {
                "total_requests": self._stats.total_requests,
                "successful": self._stats.successful_requests,
                "failed": self._stats.failed_requests,
                "rejected": self._stats.rejected_requests,
                "consecutive_failures": self._stats.consecutive_failures,
                "consecutive_successes": self._stats.consecutive_successes,
                "state_changes": self._stats.state_changes,
                "time_in_open_seconds": round(self._stats.time_in_open, 1)
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "recovery_timeout": self.config.recovery_timeout
            }
        }


class CircuitBreakerRegistry:
    """
    Registry for managing circuit breakers across all sources.

    Usage:
        registry = CircuitBreakerRegistry()
        breaker = registry.get_or_create("mangadex")

        if breaker.can_execute():
            # make request
    """

    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._default_config = default_config or CircuitBreakerConfig()

    def get_or_create(
        self,
        source_id: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one."""
        with self._lock:
            if source_id not in self._breakers:
                self._breakers[source_id] = CircuitBreaker(
                    source_id,
                    config or self._default_config
                )
            return self._breakers[source_id]

    def get(self, source_id: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker if it exists."""
        return self._breakers.get(source_id)

    def reset(self, source_id: str) -> bool:
        """Reset a specific circuit breaker."""
        breaker = self._breakers.get(source_id)
        if breaker:
            breaker.reset()
            return True
        return False

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        open_count = sum(1 for b in self._breakers.values() if b.is_open)
        half_open_count = sum(1 for b in self._breakers.values() if b.state == CircuitState.HALF_OPEN)

        return {
            "total_breakers": len(self._breakers),
            "open_count": open_count,
            "half_open_count": half_open_count,
            "closed_count": len(self._breakers) - open_count - half_open_count,
            "breakers": {
                source_id: breaker.get_status()
                for source_id, breaker in self._breakers.items()
            }
        }

    def get_available_sources(self) -> list:
        """Get list of source IDs where circuit is not open."""
        return [
            source_id for source_id, breaker in self._breakers.items()
            if not breaker.is_open
        ]
