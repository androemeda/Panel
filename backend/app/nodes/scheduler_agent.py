"""Scheduler agent."""

from __future__ import annotations

from ..schemas import ProposedSlots, TimeSlot
from ..services.calendar_mock import find_free_slots


def propose_interview_slots(
    candidate_id: str,
    held_slots: list[TimeSlot],
    limit: int = 3,
) -> ProposedSlots:
    return ProposedSlots(
        candidate_id=candidate_id,
        slots=find_free_slots(held_slots=held_slots, limit=limit),
    )
