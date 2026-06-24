"""Evaluation scenarios (Section 14).

Eight evaluation scenarios for the recruiting + screening pipeline. Tests are split
into two groups:

* **Deterministic** scenarios run with no API keys — they exercise parsing,
  scheduling, the outreach graph (which falls back to template drafts when no LLM
  key is present), the approval gate, and pool/reset semantics.
* **Full-pipeline** scenarios (strong match, mismatch, retrieval correctness,
  tie-break) require ``OPENAI_API_KEY`` (+ ``PINECONE_API_KEY`` for ranking). They
  are skipped automatically when those keys are absent, so the suite is always
  green on a fresh checkout and becomes a real end-to-end check once keys exist.

Run from ``backend/``:  ``.venv/bin/python -m pytest tests -v``
"""

from __future__ import annotations

import pytest

from app.graphs.outreach_graph import (
    resume_outreach_after_approval,
    run_outreach_until_interrupt,
)
from app.nodes.jd_parser import parse_jd
from app.nodes.scheduler_agent import propose_interview_slots
from app.schemas import (
    CandidateProfile,
    RankedCandidate,
    Shortlist,
    TimeSlot,
)
from app.services.calendar_mock import find_free_slots, load_availability
from app.services.email_mock import list_sent_emails
from app.services.store import session_store
from app.state import PipelineState

from .conftest import requires_full_pipeline

JD_SENIOR_BACKEND = "job_descriptions/jd_senior_backend.txt"
JD_JUNIOR_FRONTEND = "job_descriptions/jd_junior_frontend.txt"
JD_SENIOR_PM = "job_descriptions/jd_senior_pm.txt"


# ---------------------------------------------------------------------------
# Helpers for building outreach state without running the ranking graph.
# ---------------------------------------------------------------------------
def _fake_candidate(candidate_id: str = "c001") -> CandidateProfile:
    return CandidateProfile(
        candidate_id=candidate_id,
        name="Test Candidate",
        email="candidate@example.test",
        skills=["Python", "Distributed Systems"],
        experience=[],
        education=["B.Tech, Test University"],
        raw_text="Test Candidate resume text.",
    )


def _fake_shortlist(candidate_id: str = "c001") -> Shortlist:
    return Shortlist(
        ranked_candidates=[
            RankedCandidate(
                candidate_id=candidate_id,
                rank=1,
                overall_score=8.5,
                recommendation="strong_yes",
                reasoning="Strong systems background relative to the pool.",
                standout_strengths=["distributed systems"],
                concerns=[],
            )
        ],
        ranking_rationale="Single candidate under evaluation.",
    )


def _outreach_state(
    candidate_id: str,
    decision: str,
    held_slots: list[TimeSlot] | None = None,
) -> PipelineState:
    return PipelineState(
        parsed_jd=None,
        candidates={candidate_id: _fake_candidate(candidate_id)},
        scorecards={},
        shortlist=_fake_shortlist(candidate_id),
        active_candidate_id=candidate_id,
        hr_decision=decision,  # type: ignore[arg-type]
        held_slots=held_slots or [],
    )


def _all_availability_windows() -> list[TimeSlot]:
    return load_availability().free_windows


def _upload(client, resume_pdfs):
    files = [
        ("files", (pdf.name, pdf.read_bytes(), "application/pdf")) for pdf in resume_pdfs
    ]
    return client.post("/api/candidates/upload", files=files)


# ===========================================================================
# Scenario 1 — Upload pool returns deterministic ids + parsed name/email.
# ===========================================================================
def test_scenario_01_upload_pool_deterministic_ids(client, resume_pdfs):
    response = _upload(client, resume_pdfs)
    assert response.status_code == 200, response.text

    candidates = response.json()["candidates"]
    assert len(candidates) == len(resume_pdfs)

    # Deterministic, zero-padded, sequential ids: c001, c002, ...
    ids = [c["candidate_id"] for c in candidates]
    assert ids == [f"c{i:03d}" for i in range(1, len(resume_pdfs) + 1)]

    for candidate, pdf in zip(candidates, resume_pdfs):
        assert candidate["filename"] == pdf.name
        assert candidate["name"].strip()  # name parsed (or candidate_id fallback)
        assert "@" in candidate["email"]  # email parsed (or *.example.test fallback)

    # Pool is visible via GET before any ranking has happened.
    listed = client.get("/api/candidates").json()["candidates"]
    assert [c["candidate_id"] for c in listed] == ids


# ===========================================================================
# Scenario 2 — Strong match: full ranking produces well-formed scorecards.
# (Requires OpenAI + Pinecone. Asserts structural invariants since the exact
#  match strength depends on live model output.)
# ===========================================================================
@requires_full_pipeline
def test_scenario_02_strong_match_scorecards(client, resume_pdfs):
    _upload(client, resume_pdfs)
    response = client.post("/api/rank", json={"jd_file": JD_SENIOR_BACKEND})
    assert response.status_code == 200, response.text
    body = response.json()

    scorecards = body["scorecards"]
    assert set(scorecards) == {f"c{i:03d}" for i in range(1, len(resume_pdfs) + 1)}

    for card in scorecards.values():
        assert card["competency_scores"], "every scorecard must have competency scores"
        assert 0 <= card["overall_score"] <= 10
        for comp in card["competency_scores"]:
            assert 1 <= comp["score"] <= 10
            assert comp["evidence"].strip(), "each competency needs evidence"

    ranked = body["shortlist"]["ranked_candidates"]
    valid = {"strong_yes", "yes", "maybe", "no"}
    assert all(rc["recommendation"] in valid for rc in ranked)
    # Shortlist covers exactly the uploaded pool.
    assert {rc["candidate_id"] for rc in ranked} == set(scorecards)


# ===========================================================================
# Scenario 3 — Clear mismatch: junior-frontend JD vs the pool yields at least
# one candidate that does not meet the minimum bar (low scores).
# ===========================================================================
@requires_full_pipeline
def test_scenario_03_mismatch_below_bar(client, resume_pdfs):
    _upload(client, resume_pdfs)
    response = client.post("/api/rank", json={"jd_file": JD_JUNIOR_FRONTEND})
    assert response.status_code == 200, response.text
    body = response.json()

    cards = list(body["scorecards"].values())
    # A genuine mismatch should surface a sub-bar candidate and a low score.
    assert any(card["meets_minimum_bar"] is False for card in cards)
    assert any(card["overall_score"] <= 6 for card in cards)


# ===========================================================================
# Scenario 4 — Retrieval correctness: a JD's retrieval query returns the right
# role-family rubric chunks at the top, not engineering-vs-PM cross-talk.
# ===========================================================================
@requires_full_pipeline
def test_scenario_04_retrieval_role_family(client):
    # PM query -> top chunk should be product manager.
    pm_query = parse_jd(_read_jd(JD_SENIOR_PM)).retrieval_query
    pm_res = client.post("/api/rubrics/query", params={"q": pm_query, "top_k": 8})
    assert pm_res.status_code == 200, pm_res.text
    pm_chunks = pm_res.json()["chunks"]
    assert pm_chunks, "expected rubric chunks for PM query"
    assert pm_chunks[0]["role_family"] == "product manager"

    # Backend query -> top chunk should be a backend engineer rubric.
    be_query = parse_jd(_read_jd(JD_SENIOR_BACKEND)).retrieval_query
    be_res = client.post("/api/rubrics/query", params={"q": be_query, "top_k": 8})
    assert be_res.status_code == 200, be_res.text
    be_chunks = be_res.json()["chunks"]
    assert be_chunks[0]["role_family"] == "backend engineer"


# ===========================================================================
# Scenario 5 — Tie-break / pool reasoning: ranking is deterministic and
# justified (non-empty comparative reasoning) across repeated runs.
# ===========================================================================
@requires_full_pipeline
def test_scenario_05_deterministic_justified_ranking(client, resume_pdfs):
    _upload(client, resume_pdfs)

    first = client.post("/api/rank", json={"jd_file": JD_SENIOR_BACKEND})
    assert first.status_code == 200, first.text
    first_body = first.json()

    order_1 = [rc["candidate_id"] for rc in first_body["shortlist"]["ranked_candidates"]]
    assert first_body["shortlist"]["ranking_rationale"].strip()
    for rc in first_body["shortlist"]["ranked_candidates"]:
        assert rc["reasoning"].strip(), "each ranked candidate needs comparative reasoning"
        # Ranks are a 1..N permutation.
    ranks = sorted(rc["rank"] for rc in first_body["shortlist"]["ranked_candidates"])
    assert ranks == list(range(1, len(ranks) + 1))

    # Re-rank the same pool/JD: temperature=0 should yield a stable ordering.
    second = client.post("/api/rank", json={"jd_file": JD_SENIOR_BACKEND})
    assert second.status_code == 200, second.text
    order_2 = [rc["candidate_id"] for rc in second.json()["shortlist"]["ranked_candidates"]]
    assert order_1 == order_2


# ===========================================================================
# Scenario 6 — No-availability branch (Branch B).
# ===========================================================================
def test_scenario_06a_calendar_no_slots_when_all_held():
    """Deterministic: holding every free window leaves no slots to offer."""
    windows = _all_availability_windows()
    assert windows, "availability fixture must have windows"

    open_slots = find_free_slots(held_slots=windows, limit=3)
    assert open_slots == []

    proposed = propose_interview_slots(candidate_id="c001", held_slots=windows)
    assert proposed.slots == []


def test_scenario_06b_outreach_flags_no_availability():
    """Graph Branch B: an invite with no free slots sets no_availability, no draft."""
    state = _outreach_state("c001", "invite", held_slots=_all_availability_windows())
    result, _interrupt = run_outreach_until_interrupt(state=state)

    assert result.no_availability is True
    assert result.draft_email is None
    # Nothing was sent.
    assert list_sent_emails() == []


# ===========================================================================
# Scenario 7 — Approval gate: no send before /approve; held_slots grows only
# after an invite approval.
# ===========================================================================
def test_scenario_07_approval_gate(client, resume_pdfs):
    # Build a real session via the API: upload, then force a known shortlist so
    # we can drive a decision without needing the ranking LLM.
    _upload(client, resume_pdfs)
    candidate_id = "c001"

    session = session_store.get_session()
    session.parsed_jd = parse_jd(_read_jd(JD_SENIOR_BACKEND))
    session.shortlist = _fake_shortlist(candidate_id)
    session.scorecards = {}  # not needed for outreach
    # decision endpoint requires non-empty scorecards + candidates; reuse profile
    from app.schemas import CompetencyScore, Scorecard

    session.scorecards = {
        candidate_id: Scorecard(
            candidate_id=candidate_id,
            competency_scores=[
                CompetencyScore(
                    competency="systems",
                    score=8,
                    rubric_level="strong",
                    evidence="ok",
                )
            ],
            overall_score=8.0,
            meets_minimum_bar=True,
            summary="ok",
        )
    }
    session_store.save_session(session)

    # 1. Decision = invite -> draft is created and paused, but NOT sent.
    decision = client.post(
        f"/api/candidates/{candidate_id}/decision", json={"decision": "invite"}
    )
    assert decision.status_code == 200, decision.text
    draft = decision.json()["draft_email"]
    assert draft is not None
    assert draft["status"] in {"draft", "edited", "approved"}
    assert draft["status"] != "sent"

    # Approval gate: nothing sent and no slots held before /approve.
    assert list_sent_emails() == []
    assert session_store.get_session().held_slots == []

    # 2. Approve -> email is sent and the invite's slots are now held.
    approve = client.post(
        f"/api/candidates/{candidate_id}/approve",
        json={"to": draft["to"], "subject": draft["subject"], "body": draft["body"]},
    )
    assert approve.status_code == 200, approve.text
    approved = approve.json()
    assert approved["draft_email"]["status"] == "sent"

    sent = list_sent_emails()
    assert len(sent) == 1
    assert sent[0].candidate_id == candidate_id

    # held_slots grew only after approval.
    assert len(approved["held_slots"]) >= 1
    assert len(session_store.get_session().held_slots) >= 1


def test_scenario_07b_rejection_holds_no_slots():
    """A rejection draft is created and sent without ever holding slots."""
    state = _outreach_state("c002", "reject")
    result, _interrupt = run_outreach_until_interrupt(state=state)
    assert result.draft_email is not None
    assert result.draft_email.email_type == "rejection"
    assert result.draft_email.status != "sent"  # paused at interrupt
    assert list_sent_emails() == []

    sent_state = resume_outreach_after_approval(
        candidate_id="c002",
        to=result.draft_email.to,
        subject=result.draft_email.subject,
        body=result.draft_email.body,
    )
    assert sent_state.draft_email.status == "sent"
    # Rejections never hold interview slots.
    assert sent_state.held_slots == []


# ===========================================================================
# Scenario 8 — Pool reset semantics.
# ===========================================================================
def test_scenario_08_reset_preserves_pool_clear_removes_it(client, resume_pdfs):
    _upload(client, resume_pdfs)
    pool_ids = [c["candidate_id"] for c in client.get("/api/candidates").json()["candidates"]]
    assert pool_ids

    # Simulate downstream artifacts existing, then a "Create Ranking" reset.
    session = session_store.get_session()
    session.shortlist = _fake_shortlist(pool_ids[0])
    session.decisions = {pool_ids[0]: "invite"}
    session_store.save_session(session)

    reset = session_store.reset_downstream_for_ranking(_read_jd(JD_SENIOR_BACKEND))
    # Downstream cleared...
    assert reset.shortlist is None
    assert reset.scorecards == {}
    assert reset.decisions == {}
    assert reset.held_slots == []
    # ...but the uploaded pool is preserved.
    assert [c.candidate_id for c in reset.candidate_pool] == pool_ids
    assert reset.candidate_inputs, "candidate inputs preserved for re-ranking"

    # Clear pool removes everything.
    cleared = client.delete("/api/candidates")
    assert cleared.status_code == 200
    assert cleared.json()["candidates"] == []
    assert session_store.get_session().candidate_pool == []


# ===========================================================================
# Supporting deterministic checks (parsing + scheduling correctness).
# ===========================================================================
@pytest.mark.parametrize(
    "jd_file, expected_family, expected_seniority",
    [
        (JD_SENIOR_BACKEND, "backend engineer", "senior"),
        (JD_JUNIOR_FRONTEND, "frontend engineer", "junior"),
        (JD_SENIOR_PM, "product manager", "senior"),
    ],
)
def test_jd_parser_detects_role_family_and_seniority(
    jd_file, expected_family, expected_seniority
):
    parsed = parse_jd(_read_jd(jd_file))
    assert parsed.role_family == expected_family
    assert parsed.seniority == expected_seniority
    assert parsed.retrieval_query.strip()
    assert parsed.required_skills, "required skills should be extracted"


def test_scheduler_offers_distinct_non_conflicting_slots():
    """Invite slots are real, ordered, and don't overlap held slots."""
    windows = _all_availability_windows()
    held = windows[:1]  # hold the earliest window
    proposed = propose_interview_slots(candidate_id="c001", held_slots=held, limit=3)

    assert 1 <= len(proposed.slots) <= 3
    starts = [s.start for s in proposed.slots]
    assert starts == sorted(starts), "slots returned in chronological order"
    held_start = held[0].start
    assert all(s.start != held_start for s in proposed.slots), "held slot not re-offered"


def test_resume_parser_fallback_extracts_email(client, resume_pdfs):
    """Even without an LLM key, parsing populates a usable email/name."""
    _upload(client, resume_pdfs)
    state = session_store.get_session()
    assert state.candidates
    for profile in state.candidates.values():
        assert "@" in profile.email
        assert profile.name.strip()


# ---------------------------------------------------------------------------
def _read_jd(relative: str) -> str:
    from app.config import BACKEND_ROOT

    return (BACKEND_ROOT / "data" / relative).read_text(encoding="utf-8")
