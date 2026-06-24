"""Single active session persistence."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, Field

from ..config import BACKEND_ROOT
from ..schemas import (
    CandidateInput,
    CandidateProfile,
    CandidateResumeItem,
    DraftEmail,
    ParsedJD,
    RetrievedRubric,
    Scorecard,
    Shortlist,
    TimeSlot,
)


STORE_PATH = BACKEND_ROOT / ".local" / "session_store.json"


class SessionState(BaseModel):
    raw_jd_text: str | None = None
    candidate_inputs: list[CandidateInput] = Field(default_factory=list)
    candidate_pool: list[CandidateResumeItem] = Field(default_factory=list)
    parsed_jd: ParsedJD | None = None
    retrieved_rubric: RetrievedRubric | None = None
    candidates: dict[str, CandidateProfile] = Field(default_factory=dict)
    scorecards: dict[str, Scorecard] = Field(default_factory=dict)
    shortlist: Shortlist | None = None
    decisions: dict[str, Literal["invite", "reject"]] = Field(default_factory=dict)
    drafts: dict[str, DraftEmail] = Field(default_factory=dict)
    no_availability: dict[str, bool] = Field(default_factory=dict)
    held_slots: list[TimeSlot] = Field(default_factory=list)
    trace_url: str | None = None
    next_candidate_number: int = 1


class SessionStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get_session(self) -> SessionState:
        with self._lock:
            return self._read()

    def save_session(self, session: SessionState) -> SessionState:
        with self._lock:
            self._write(session)
        return session

    def add_candidates(
        self,
        uploads: list[tuple[str, str, CandidateInput, CandidateProfile]],
    ) -> SessionState:
        with self._lock:
            session = self._read()
            for filename, candidate_id, candidate_input, profile in uploads:
                session.candidate_inputs.append(candidate_input)
                session.candidate_pool.append(
                    CandidateResumeItem(
                        candidate_id=candidate_id,
                        filename=filename,
                        name=profile.name,
                        email=profile.email,
                    )
                )
                session.candidates[candidate_id] = profile
            if uploads:
                session.next_candidate_number = max(
                    session.next_candidate_number,
                    max(int(candidate_id[1:]) for _, candidate_id, _, _ in uploads) + 1,
                )
            self._clear_downstream(session)
            self._write(session)
            return session

    def remove_candidate(self, candidate_id: str) -> SessionState | None:
        with self._lock:
            session = self._read()
            if candidate_id not in {item.candidate_id for item in session.candidate_pool}:
                return None
            session.candidate_pool = [
                item for item in session.candidate_pool if item.candidate_id != candidate_id
            ]
            session.candidate_inputs = [
                item for item in session.candidate_inputs if item.candidate_id != candidate_id
            ]
            session.candidates.pop(candidate_id, None)
            self._clear_downstream(session)
            self._write(session)
            return session

    def clear_pool(self) -> SessionState:
        session = SessionState()
        return self.save_session(session)

    def reset_downstream_for_ranking(self, raw_jd_text: str) -> SessionState:
        with self._lock:
            session = self._read()
            session.raw_jd_text = raw_jd_text
            self._clear_downstream(session)
            self._write(session)
            return session

    def save_ranking_outputs(
        self,
        *,
        parsed_jd: ParsedJD,
        retrieved_rubric: RetrievedRubric,
        candidates: dict[str, CandidateProfile],
        scorecards: dict[str, Scorecard],
        shortlist: Shortlist,
        trace_url: str | None = None,
    ) -> SessionState:
        with self._lock:
            session = self._read()
            session.parsed_jd = parsed_jd
            session.retrieved_rubric = retrieved_rubric
            session.candidates = candidates
            session.scorecards = scorecards
            session.shortlist = shortlist
            session.trace_url = trace_url
            for item in session.candidate_pool:
                profile = candidates.get(item.candidate_id)
                if profile:
                    item.name = profile.name
                    item.email = profile.email
            self._write(session)
            return session

    def _clear_downstream(self, session: SessionState) -> None:
        session.parsed_jd = None
        session.retrieved_rubric = None
        session.scorecards = {}
        session.shortlist = None
        session.decisions = {}
        session.drafts = {}
        session.no_availability = {}
        session.held_slots = []
        session.trace_url = None

    def _read(self) -> SessionState:
        if not self.path.exists():
            return SessionState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        session = SessionState.model_validate(raw)
        if any(item.resume_file for item in session.candidate_pool):
            return SessionState()
        return session

    def _write(self, session: SessionState) -> None:
        self.path.write_text(
            json.dumps(session.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )


session_store = SessionStore()
