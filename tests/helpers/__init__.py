"""Test helpers for GUI and SDN controller tests."""

from __future__ import annotations

import time
from collections.abc import Callable


def wait_until(condition: Callable[[], bool], timeout: float = 5.0, interval: float = 0.01) -> None:
    """Wait until *condition* returns True (polling loop with timeout).

    Replaces fixed ``time.sleep()`` with conditional polling — reduces
    flakiness because the test proceeds as soon as the condition is met.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise TimeoutError(f"Condition not met within {timeout}s")
