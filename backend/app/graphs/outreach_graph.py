"""Graph 2: HR decision routing, scheduling, outreach drafting, and approval."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from typing import Any, Literal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ..config import BACKEND_ROOT
from ..nodes.outreach_agent import draft_outreach_email
from ..nodes.scheduler_agent import propose_interview_slots
from ..schemas import CandidateProfile, DraftEmail, RankedCandidate, TimeSlot
from ..services.email_mock import send_email
from ..state import PipelineState


CHECKPOINT_PATH = BACKEND_ROOT / ".local" / "outreach_checkpoints.sqlite"


def _state(value: PipelineState | dict[str, Any]) -> PipelineState:
    if isinstance(value, PipelineState):
        return value
    return PipelineState.model_validate(value)


def _candidate(state: PipelineState) -> CandidateProfile:
    if state.active_candidate_id is None:
        raise ValueError("active_candidate_id is required")
    try:
        return state.candidates[state.active_candidate_id]
    except KeyError as exc:
        raise ValueError(f"Candidate not found: {state.active_candidate_id}") from exc


def _ranked_candidate(state: PipelineState) -> RankedCandidate:
    if state.active_candidate_id is None:
        raise ValueError("active_candidate_id is required")
    if state.shortlist is None:
        raise ValueError("shortlist is required before outreach")
    for ranked in state.shortlist.ranked_candidates:
        if ranked.candidate_id == state.active_candidate_id:
            return ranked
    raise ValueError(f"Ranked candidate not found: {state.active_candidate_id}")


def decision_router_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.hr_decision not in {"invite", "reject"}:
        raise ValueError("hr_decision must be invite or reject")
    return {}


def route_decision(state: PipelineState | dict[str, Any]) -> Literal["invite", "reject"]:
    current = _state(state)
    if current.hr_decision not in {"invite", "reject"}:
        raise ValueError("hr_decision must be invite or reject")
    return current.hr_decision


def scheduler_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.active_candidate_id is None:
        raise ValueError("active_candidate_id is required")
    return {
        "proposed_slots": propose_interview_slots(
            candidate_id=current.active_candidate_id,
            held_slots=current.held_slots,
        )
    }


def route_availability(state: PipelineState | dict[str, Any]) -> Literal["slots_found", "none"]:
    current = _state(state)
    if current.proposed_slots and current.proposed_slots.slots:
        return "slots_found"
    return "none"


def flag_no_availability_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    return {"no_availability": True, "draft_email": None}


def draft_invite_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.proposed_slots is None or not current.proposed_slots.slots:
        raise ValueError("proposed_slots are required for invite drafts")
    draft = draft_outreach_email(
        candidate=_candidate(current),
        ranked_candidate=_ranked_candidate(current),
        decision="invite",
        proposed_slots=current.proposed_slots,
    )
    return {"draft_email": draft, "no_availability": False}


def draft_rejection_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    draft = draft_outreach_email(
        candidate=_candidate(current),
        ranked_candidate=_ranked_candidate(current),
        decision="reject",
        proposed_slots=None,
    )
    return {"draft_email": draft, "no_availability": False}


def human_review_interrupt_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.draft_email is None:
        raise ValueError("draft_email is required before human review")

    approval = interrupt(current.draft_email.model_dump(mode="json"))
    if not isinstance(approval, dict):
        raise ValueError("Approval payload must be an object")

    subject = approval.get("subject") or current.draft_email.subject
    body = approval.get("body") or current.draft_email.body
    approved_draft = current.draft_email.model_copy(
        update={
            "subject": subject,
            "body": body,
            "status": "approved",
        }
    )
    return {"draft_email": approved_draft}


def _slot_key(slot: TimeSlot) -> tuple[str, str]:
    return (slot.start.isoformat(), slot.end.isoformat())


def _append_unique_slots(existing: list[TimeSlot], new_slots: list[TimeSlot]) -> list[TimeSlot]:
    seen = {_slot_key(slot) for slot in existing}
    combined = list(existing)
    for slot in new_slots:
        key = _slot_key(slot)
        if key not in seen:
            combined.append(slot)
            seen.add(key)
    return combined


def send_email_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.draft_email is None:
        raise ValueError("draft_email is required before sending")
    if current.draft_email.status != "approved":
        raise ValueError("draft_email must be approved before sending")

    sent_email = send_email(current.draft_email)
    updates: dict[str, Any] = {"draft_email": sent_email}

    if sent_email.email_type == "invite" and sent_email.proposed_slots:
        updates["held_slots"] = _append_unique_slots(
            current.held_slots,
            sent_email.proposed_slots,
        )

    return updates


def _build_checkpointer() -> SqliteSaver:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


@lru_cache
def build_outreach_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("decision_router", decision_router_node)
    graph.add_node("scheduler_agent", scheduler_node)
    graph.add_node("flag_no_availability", flag_no_availability_node)
    graph.add_node("draft_invite", draft_invite_node)
    graph.add_node("draft_rejection", draft_rejection_node)
    graph.add_node("human_review_interrupt", human_review_interrupt_node)
    graph.add_node("send_email", send_email_node)

    graph.add_edge(START, "decision_router")
    graph.add_conditional_edges(
        "decision_router",
        route_decision,
        {
            "invite": "scheduler_agent",
            "reject": "draft_rejection",
        },
    )
    graph.add_conditional_edges(
        "scheduler_agent",
        route_availability,
        {
            "slots_found": "draft_invite",
            "none": "flag_no_availability",
        },
    )
    graph.add_edge("draft_invite", "human_review_interrupt")
    graph.add_edge("draft_rejection", "human_review_interrupt")
    graph.add_edge("human_review_interrupt", "send_email")
    graph.add_edge("send_email", END)
    graph.add_edge("flag_no_availability", END)
    return graph.compile(checkpointer=_build_checkpointer())


def thread_id_for(candidate_id: str) -> str:
    return candidate_id


def _extract_interrupt_value(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    return first.value


def run_outreach_until_interrupt(
    *,
    state: PipelineState,
) -> tuple[PipelineState, dict[str, Any] | None]:
    if state.active_candidate_id is None:
        raise ValueError("active_candidate_id is required")

    graph = build_outreach_graph()
    config = {
        "configurable": {
            "thread_id": thread_id_for(state.active_candidate_id),
        },
        "run_name": "outreach_graph",
        "metadata": {
            "candidate_id": state.active_candidate_id,
            "decision": state.hr_decision,
        },
    }
    result = graph.invoke(state, config=config)
    interrupt_value = _extract_interrupt_value(result)
    return _state(result), interrupt_value


def resume_outreach_after_approval(
    *,
    candidate_id: str,
    subject: str,
    body: str,
) -> PipelineState:
    graph = build_outreach_graph()
    config = {
        "configurable": {
            "thread_id": thread_id_for(candidate_id),
        },
        "run_name": "outreach_graph_approval",
        "metadata": {
            "candidate_id": candidate_id,
        },
    }
    result = graph.invoke(
        Command(resume={"subject": subject, "body": body}),
        config=config,
    )
    if "__interrupt__" in result:
        raise ValueError("Outreach graph paused again instead of sending")
    return _state(result)
