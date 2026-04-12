# @forgeplan-node: core-infrastructure
"""
Tests for case_activity_events bus — AC9.

Tests that publish_case_activity_event delivers events to subscribers with
all required fields: actor_user_id, event_type, old_status, new_status, occurred_at.
"""
# @forgeplan-spec: AC9

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone

from placementops.core.events import (
    CaseActivityEvent,
    publish_case_activity_event,
    subscribe_case_activity,
    unsubscribe_case_activity,
    _subscribers,
)
from placementops.core.state_machine import transition_case_status

pytestmark = pytest.mark.asyncio


async def test_subscriber_receives_event():
    """AC9: Handler registered via subscribe_case_activity receives published events."""
    received: list[CaseActivityEvent] = []

    async def handler(event: CaseActivityEvent) -> None:
        received.append(event)

    subscribe_case_activity(handler)
    try:
        event = CaseActivityEvent(
            case_id=uuid4(),
            actor_user_id=uuid4(),
            event_type="status_changed",
            old_status="new",
            new_status="intake_in_progress",
        )
        await publish_case_activity_event(event)
        assert len(received) == 1
        assert received[0] is event
    finally:
        unsubscribe_case_activity(handler)


async def test_event_contains_required_fields():
    """AC9: Published event has actor_user_id, event_type, old_status, new_status, occurred_at."""
    received: list[CaseActivityEvent] = []

    async def handler(event: CaseActivityEvent) -> None:
        received.append(event)

    subscribe_case_activity(handler)
    try:
        actor_id = uuid4()
        case_id = uuid4()
        event = CaseActivityEvent(
            case_id=case_id,
            actor_user_id=actor_id,
            event_type="status_changed",
            old_status="intake_in_progress",
            new_status="intake_complete",
        )
        await publish_case_activity_event(event)

        assert len(received) == 1
        e = received[0]
        # AC9 required fields
        assert e.actor_user_id == actor_id
        assert e.event_type == "status_changed"
        assert e.old_status == "intake_in_progress"
        assert e.new_status == "intake_complete"
        assert isinstance(e.occurred_at, datetime)
    finally:
        unsubscribe_case_activity(handler)


async def test_transition_triggers_event_publication(db_session, patient_case, user):
    """AC9: State transition via transition_case_status publishes event to bus."""
    received: list[CaseActivityEvent] = []

    async def handler(event: CaseActivityEvent) -> None:
        received.append(event)

    subscribe_case_activity(handler)
    try:
        await transition_case_status(
            case_id=UUID(patient_case.id),
            to_status="intake_in_progress",
            actor_role="intake_staff",
            actor_user_id=UUID(user.id),
            session=db_session,
            organization_id=UUID(patient_case.organization_id),
        )

        assert len(received) == 1
        event = received[0]
        assert event.event_type == "status_changed"
        assert event.old_status == "new"
        assert event.new_status == "intake_in_progress"
        assert event.actor_user_id == UUID(user.id)
        assert event.occurred_at is not None
    finally:
        unsubscribe_case_activity(handler)


async def test_handler_error_does_not_propagate(db_session, patient_case, user):
    """Handler exceptions are caught and logged; they do not fail the transition."""
    async def bad_handler(event: CaseActivityEvent) -> None:
        raise RuntimeError("Handler exploded")

    subscribe_case_activity(bad_handler)
    try:
        # Should NOT raise — handler errors are swallowed
        updated_case = await transition_case_status(
            case_id=UUID(patient_case.id),
            to_status="intake_in_progress",
            actor_role="intake_staff",
            actor_user_id=UUID(user.id),
            session=db_session,
            organization_id=UUID(patient_case.organization_id),
        )
        assert updated_case.current_status == "intake_in_progress"
    finally:
        unsubscribe_case_activity(bad_handler)


async def test_multiple_subscribers_all_receive_event():
    """Multiple subscribers all receive the same event."""
    received_a: list[CaseActivityEvent] = []
    received_b: list[CaseActivityEvent] = []

    async def handler_a(event: CaseActivityEvent) -> None:
        received_a.append(event)

    async def handler_b(event: CaseActivityEvent) -> None:
        received_b.append(event)

    subscribe_case_activity(handler_a)
    subscribe_case_activity(handler_b)
    try:
        event = CaseActivityEvent(
            case_id=uuid4(),
            actor_user_id=uuid4(),
            event_type="status_changed",
            old_status="new",
            new_status="intake_in_progress",
        )
        await publish_case_activity_event(event)

        assert len(received_a) == 1
        assert len(received_b) == 1
    finally:
        unsubscribe_case_activity(handler_a)
        unsubscribe_case_activity(handler_b)


async def test_unsubscribe_removes_handler():
    """Unsubscribed handler no longer receives events."""
    received: list[CaseActivityEvent] = []

    async def handler(event: CaseActivityEvent) -> None:
        received.append(event)

    subscribe_case_activity(handler)
    unsubscribe_case_activity(handler)

    event = CaseActivityEvent(
        case_id=uuid4(),
        actor_user_id=uuid4(),
        event_type="status_changed",
        old_status="new",
        new_status="intake_in_progress",
    )
    await publish_case_activity_event(event)
    assert len(received) == 0
