"""Mock calendar service."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import BACKEND_ROOT
from ..schemas import TimeSlot


AVAILABILITY_PATH = BACKEND_ROOT / "data" / "availability.json"


class Availability(BaseModel):
    interviewer: str
    timezone: str
    free_windows: list[TimeSlot] = Field(default_factory=list)


def load_availability(path: Path | str = AVAILABILITY_PATH) -> Availability:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Availability.model_validate(raw)


def slots_overlap(left: TimeSlot, right: TimeSlot) -> bool:
    return left.start < right.end and right.start < left.end


def subtract_held_slots(
    free_windows: list[TimeSlot],
    held_slots: list[TimeSlot],
) -> list[TimeSlot]:
    return [
        window
        for window in free_windows
        if not any(slots_overlap(window, held) for held in held_slots)
    ]


def find_free_slots(
    held_slots: list[TimeSlot],
    limit: int = 3,
    availability_path: Path | str = AVAILABILITY_PATH,
) -> list[TimeSlot]:
    availability = load_availability(availability_path)
    open_windows = subtract_held_slots(
        sorted(availability.free_windows, key=lambda slot: slot.start),
        held_slots,
    )
    return open_windows[:limit]
