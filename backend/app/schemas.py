"""Pydantic contracts for graph inputs and outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class JDRequirement(BaseModel):
    skill: str
    importance: Literal["required", "preferred"]


class ParsedJD(BaseModel):
    role_title: str
    role_family: str
    seniority: Literal["intern", "junior", "mid", "senior"]
    required_skills: list[JDRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    retrieval_query: str


class RubricChunk(BaseModel):
    role_family: str
    seniority: str
    competency: str
    strong_descriptor: str
    average_descriptor: str
    weak_descriptor: str
    red_flags: list[str]
    score: float | None = None


class RetrievedRubric(BaseModel):
    chunks: list[RubricChunk] = Field(default_factory=list)
    query_used: str


class CandidateInput(BaseModel):
    candidate_id: str
    raw_resume_text: str


class CandidateResumeItem(BaseModel):
    candidate_id: str
    filename: str = ""
    name: str = ""
    email: str = ""
    resume_file: str | None = None


class CandidatePoolResponse(BaseModel):
    candidates: list[CandidateResumeItem] = Field(default_factory=list)


class WorkExperience(BaseModel):
    title: str
    company: str
    duration_months: int
    highlights: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    candidate_id: str
    name: str
    email: str
    skills: list[str] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    raw_text: str


class CompetencyScore(BaseModel):
    competency: str
    score: int = Field(ge=1, le=10)
    rubric_level: Literal["strong", "average", "weak"]
    evidence: str


class Scorecard(BaseModel):
    candidate_id: str
    competency_scores: list[CompetencyScore] = Field(default_factory=list)
    overall_score: float
    meets_minimum_bar: bool
    summary: str


class RankedCandidate(BaseModel):
    candidate_id: str
    rank: int
    overall_score: float
    recommendation: Literal["strong_yes", "yes", "maybe", "no"]
    reasoning: str
    standout_strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class Shortlist(BaseModel):
    ranked_candidates: list[RankedCandidate] = Field(default_factory=list)
    ranking_rationale: str


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class ProposedSlots(BaseModel):
    candidate_id: str
    slots: list[TimeSlot] = Field(default_factory=list)


class DraftEmail(BaseModel):
    candidate_id: str
    email_type: Literal["invite", "rejection"]
    to: str
    subject: str
    body: str
    proposed_slots: list[TimeSlot] | None = None
    status: Literal["draft", "edited", "approved", "sent"] = "draft"


class CandidateDecisionRequest(BaseModel):
    decision: Literal["invite", "reject"]


class CandidateDecisionResponse(BaseModel):
    candidate_id: str
    decision: Literal["invite", "reject"]
    thread_id: str
    draft_email: DraftEmail | None = None
    proposed_slots: ProposedSlots | None = None
    no_availability: bool = False


class ApproveDraftRequest(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str | None = None


class ApproveDraftResponse(BaseModel):
    candidate_id: str
    thread_id: str
    draft_email: DraftEmail
    held_slots: list[TimeSlot] = Field(default_factory=list)


class ParseJDRequest(BaseModel):
    raw_jd_text: str


class ParseResumeTextRequest(BaseModel):
    candidate_id: str
    raw_resume_text: str


class ParseResumeFileRequest(BaseModel):
    candidate_id: str
    resume_file: str


class RankRequest(BaseModel):
    raw_jd_text: str | None = None
    jd_file: str | None = None


class RankResponse(BaseModel):
    candidate_pool: list[CandidateResumeItem] = Field(default_factory=list)
    parsed_jd: ParsedJD
    retrieved_rubric: RetrievedRubric
    candidates: dict[str, CandidateProfile]
    scorecards: dict[str, Scorecard]
    shortlist: Shortlist
    trace_url: str | None = None


class StateResponse(BaseModel):
    raw_jd_text: str | None = None
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
