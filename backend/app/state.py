"""Shared LangGraph state and reducers."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .schemas import (
    CandidateInput,
    CandidateProfile,
    DraftEmail,
    ParsedJD,
    ProposedSlots,
    RetrievedRubric,
    Scorecard,
    Shortlist,
    TimeSlot,
)


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class PipelineState(BaseModel):
    raw_jd_text: str | None = None
    parsed_jd: ParsedJD | None = None
    retrieved_rubric: RetrievedRubric | None = None
    candidate_input: CandidateInput | None = None
    candidate_inputs: list[CandidateInput] = Field(default_factory=list)
    candidates: Annotated[dict[str, CandidateProfile], merge_dicts] = Field(
        default_factory=dict
    )
    scorecards: Annotated[dict[str, Scorecard], merge_dicts] = Field(default_factory=dict)
    shortlist: Shortlist | None = None

    active_candidate_id: str | None = None
    hr_decision: Literal["invite", "reject"] | None = None
    proposed_slots: ProposedSlots | None = None
    held_slots: list[TimeSlot] = Field(default_factory=list)
    draft_email: DraftEmail | None = None
    no_availability: bool = False
