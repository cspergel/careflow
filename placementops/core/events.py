# @forgeplan-node: core-infrastructure
"""
In-process event bus for case activity events.

Provides a lightweight pub/sub mechanism for case state transitions.
Subscribers register handlers; publisher emits CaseActivityEvent instances.

This is an in-process bus only — no external message broker in Phase 1.
"""
# @forgeplan-spec: AC9
# @forgeplan-decision: D-core-3-in-process-bus -- In-process list of async handlers (no external broker). Why: Phase 1 scope; FastAPI BackgroundTasks can invoke handlers without introducing Redis/Celery dependency; the bus interface is stable so Phase 2 can swap the backend transparently

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Awaitable
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CaseActivityEvent:
    """
    Event published for every case state transition.

    Required fields per AC9: actor_user_id, event_type, old_status, new_status, occurred_at.
    """

    case_id: UUID
    actor_user_id: UUID
    event_type: str  # e.g. "status_changed"
    old_status: str | None
    new_status: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    organization_id: UUID | None = None
    metadata: dict = field(default_factory=dict)


# Type alias for event handler functions
CaseActivityHandler = Callable[[CaseActivityEvent], Awaitable[None]]

# In-process subscriber registry
_subscribers: list[CaseActivityHandler] = []


def subscribe_case_activity(handler: CaseActivityHandler) -> None:
    """Register an async handler to receive CaseActivityEvent instances."""
    _subscribers.append(handler)


def unsubscribe_case_activity(handler: CaseActivityHandler) -> None:
    """Remove a previously registered handler."""
    try:
        _subscribers.remove(handler)
    except ValueError:
        pass


async def publish_case_activity_event(event: CaseActivityEvent) -> None:
    """
    Publish a case activity event to all registered subscribers.

    Each handler is called concurrently via asyncio.gather.
    Handler errors are logged but do not propagate to the caller —
    event publication must not fail a status transition.
    """
    # @forgeplan-spec: AC9
    if not _subscribers:
        return

    async def _safe_call(handler: CaseActivityHandler) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "case_activity_events handler %s raised an exception for event %s",
                handler,
                event.event_type,
            )

    await asyncio.gather(*(_safe_call(h) for h in _subscribers))


# Expose the subscriber list for testing (read-only — tests may inspect, not modify directly)
case_activity_events = _subscribers
