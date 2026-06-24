"""Outreach agent."""

from __future__ import annotations

import json

from ..llm import get_llm
from ..schemas import CandidateProfile, DraftEmail, ProposedSlots, RankedCandidate, TimeSlot


def _format_slot(slot: TimeSlot) -> str:
    return f"{slot.start.isoformat()} to {slot.end.isoformat()}"


def _fallback_draft(
    candidate: CandidateProfile,
    ranked_candidate: RankedCandidate,
    decision: str,
    proposed_slots: ProposedSlots | None,
) -> DraftEmail:
    if decision == "invite":
        slot_lines = "\n".join(
            f"- {_format_slot(slot)}" for slot in (proposed_slots.slots if proposed_slots else [])
        )
        return DraftEmail(
            candidate_id=candidate.candidate_id,
            email_type="invite",
            to=candidate.email,
            subject="Interview invitation",
            body=(
                f"Hi {candidate.name},\n\n"
                "Thank you for your interest in the role. We would like to invite you "
                "to an interview. Please let us know which of these slots works best:\n\n"
                f"{slot_lines}\n\n"
                "Best,\nRecruiting Team"
            ),
            proposed_slots=proposed_slots.slots if proposed_slots else [],
            status="draft",
        )

    return DraftEmail(
        candidate_id=candidate.candidate_id,
        email_type="rejection",
        to=candidate.email,
        subject="Update on your application",
        body=(
            f"Hi {candidate.name},\n\n"
            "Thank you for taking the time to apply. After reviewing your profile "
            "against the current role requirements, we will not be moving forward "
            "at this time.\n\n"
            "We appreciate your interest and wish you the best in your search.\n\n"
            "Best,\nRecruiting Team"
        ),
        proposed_slots=None,
        status="draft",
    )


def draft_outreach_email(
    candidate: CandidateProfile,
    ranked_candidate: RankedCandidate,
    decision: str,
    proposed_slots: ProposedSlots | None = None,
) -> DraftEmail:
    payload = {
        "candidate": candidate.model_dump(),
        "ranked_candidate": ranked_candidate.model_dump(),
        "decision": decision,
        "proposed_slots": proposed_slots.model_dump() if proposed_slots else None,
    }

    try:
        structured_llm = get_llm().with_structured_output(DraftEmail)
        result = structured_llm.invoke(
            [
                (
                    "system",
                    (
                        "You are the Outreach Agent for a recruiter. Draft concise, "
                        "professional emails that HR can edit before approval. "
                        "Do not imply anything has been scheduled or sent. For invite "
                        "emails, include every proposed slot exactly. For rejections, "
                        "be respectful, do not claim an interview already happened, and "
                        "do not over-explain or mention internal scores. Never use "
                        "placeholders like [Your Name]; sign as Priya Nair, Recruiting Team."
                    ),
                ),
                (
                    "human",
                    "Return a valid DraftEmail for this candidate and decision:\n"
                    f"{json.dumps(payload, indent=2, default=str)}",
                ),
            ]
        )
        draft = result if isinstance(result, DraftEmail) else DraftEmail.model_validate(result)
    except Exception:
        draft = _fallback_draft(candidate, ranked_candidate, decision, proposed_slots)

    updates = {
        "candidate_id": candidate.candidate_id,
        "to": candidate.email,
        "status": "draft",
    }

    if decision == "invite":
        updates["email_type"] = "invite"
        updates["proposed_slots"] = proposed_slots.slots if proposed_slots else []
    else:
        updates["email_type"] = "rejection"
        updates["proposed_slots"] = None

    return draft.model_copy(update=updates)
