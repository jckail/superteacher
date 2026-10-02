"""Shared, fail-fast AI admission per event loop (one loop per server worker).

No waiter queue: a generation task/client is allocated only after admission.
Hold leases through retries, tool rounds and bounded client cleanup.
"""

from __future__ import annotations

import asyncio
import weakref
from contextlib import suppress
from dataclasses import dataclass

from .config import get_settings


class CapacityError(Exception):
    """The worker already has its maximum admitted AI operations."""


@dataclass
class _Budget:
    active: int = 0


_budgets: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Budget] = weakref.WeakKeyDictionary()


class Lease:
    def __init__(self, budget: _Budget):
        self.budget = budget
        self.released = False

    def release(self) -> None:
        if not self.released:
            self.released = True
            self.budget.active -= 1


def acquire() -> Lease:
    loop = asyncio.get_running_loop()
    budget = _budgets.setdefault(loop, _Budget())
    if budget.active >= get_settings().ai_max_concurrent_requests:
        raise CapacityError("The AI service is busy. Please try again in a moment.")
    budget.active += 1
    return Lease(budget)


async def close_client(client) -> None:
    """Bound transport cleanup so it cannot retain a capacity lease forever."""
    # Preserve the response or original cancellation on cleanup failure.
    with suppress(Exception):
        await asyncio.wait_for(client.close(), timeout=5.0)
