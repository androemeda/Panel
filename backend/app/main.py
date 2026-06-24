from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import BACKEND_ROOT, get_settings
from .graphs.outreach_graph import (
    resume_outreach_after_approval,
    run_outreach_until_interrupt,
    thread_id_for,
)
from .graphs.ranking_graph import run_ranking_graph
from .nodes.jd_parser import parse_jd
from .nodes.resume_parser import (
    extract_resume_text_from_bytes,
    parse_resume,
    parse_resume_file,
)
from .schemas import (
    ApproveDraftRequest,
    ApproveDraftResponse,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    CandidateInput,
    CandidatePoolResponse,
    CandidateProfile,
    ParsedJD,
    ParseJDRequest,
    ParseResumeFileRequest,
    ParseResumeTextRequest,
    ProposedSlots,
    RankRequest,
    RankResponse,
    RetrievedRubric,
    StateResponse,
)
from .services.store import SessionState, session_store
from .state import PipelineState
from .vectordb import MissingConfigurationError, query_rubrics


settings = get_settings()

app = FastAPI(
    title="AI Recruiting and Candidate Screening Pipeline",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATA_ROOT = BACKEND_ROOT / "data"


def _resolve_data_file(relative_path: str) -> Path:
    path = (DATA_ROOT / relative_path).resolve()
    data_root = DATA_ROOT.resolve()
    if data_root not in path.parents and path != data_root:
        raise ValueError("File must live under backend/data")
    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    return path


def _resolve_jd_text(payload: RankRequest) -> str:
    if payload.raw_jd_text and payload.raw_jd_text.strip():
        return payload.raw_jd_text
    if payload.jd_file:
        return _resolve_data_file(payload.jd_file).read_text(encoding="utf-8")
    raise ValueError("Provide raw_jd_text or jd_file")


def _state_response(session: SessionState) -> StateResponse:
    return StateResponse(
        raw_jd_text=session.raw_jd_text,
        candidate_pool=session.candidate_pool,
        parsed_jd=session.parsed_jd,
        retrieved_rubric=session.retrieved_rubric,
        candidates=session.candidates,
        scorecards=session.scorecards,
        shortlist=session.shortlist,
        decisions=session.decisions,
        drafts=session.drafts,
        no_availability=session.no_availability,
        held_slots=session.held_slots,
        trace_url=session.trace_url,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "recruiting-pipeline"}


@app.get("/api/state", response_model=StateResponse)
def get_state() -> StateResponse:
    return _state_response(session_store.get_session())


@app.get("/api/candidates", response_model=CandidatePoolResponse)
def get_candidates() -> CandidatePoolResponse:
    session = session_store.get_session()
    return CandidatePoolResponse(candidates=session.candidate_pool)


@app.post("/api/candidates/upload", response_model=CandidatePoolResponse)
async def upload_candidates(files: list[UploadFile] = File(...)) -> CandidatePoolResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one resume PDF")

    session = session_store.get_session()
    next_number = session.next_candidate_number
    uploads = []

    try:
        for index, file in enumerate(files):
            filename = file.filename or f"resume_{index + 1}.pdf"
            if not filename.lower().endswith(".pdf"):
                raise ValueError(f"Only PDF uploads are supported: {filename}")

            candidate_id = f"c{next_number + index:03d}"
            content = await file.read()
            raw_resume_text = extract_resume_text_from_bytes(filename, content)
            candidate_input = CandidateInput(
                candidate_id=candidate_id,
                raw_resume_text=raw_resume_text,
            )
            profile = parse_resume(candidate_input, use_llm=True)
            uploads.append((filename, candidate_id, candidate_input, profile))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for file in files:
            await file.close()

    updated = session_store.add_candidates(uploads)
    return CandidatePoolResponse(candidates=updated.candidate_pool)


@app.delete("/api/candidates", response_model=CandidatePoolResponse)
def clear_candidates() -> CandidatePoolResponse:
    session = session_store.clear_pool()
    return CandidatePoolResponse(candidates=session.candidate_pool)


@app.delete("/api/candidates/{candidate_id}", response_model=CandidatePoolResponse)
def delete_candidate(candidate_id: str) -> CandidatePoolResponse:
    session = session_store.remove_candidate(candidate_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Candidate not found in pool")
    return CandidatePoolResponse(candidates=session.candidate_pool)


@app.post("/api/rank", response_model=RankResponse)
def rank_candidates(payload: RankRequest) -> RankResponse:
    try:
        raw_jd_text = _resolve_jd_text(payload)
        session = session_store.reset_downstream_for_ranking(raw_jd_text)
        if not session.candidate_inputs:
            raise ValueError("Upload at least one candidate resume before ranking")

        graph_state = run_ranking_graph(
            raw_jd_text=session.raw_jd_text or "",
            candidate_inputs=session.candidate_inputs,
        )
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if (
        graph_state.parsed_jd is None
        or graph_state.retrieved_rubric is None
        or graph_state.shortlist is None
    ):
        raise HTTPException(status_code=500, detail="Ranking graph returned incomplete state")

    session = session_store.save_ranking_outputs(
        parsed_jd=graph_state.parsed_jd,
        retrieved_rubric=graph_state.retrieved_rubric,
        candidates=graph_state.candidates,
        scorecards=graph_state.scorecards,
        shortlist=graph_state.shortlist,
        trace_url=session.trace_url,
    )

    return RankResponse(
        candidate_pool=session.candidate_pool,
        parsed_jd=session.parsed_jd,
        retrieved_rubric=session.retrieved_rubric,
        candidates=session.candidates,
        scorecards=session.scorecards,
        shortlist=session.shortlist,
        trace_url=session.trace_url,
    )


@app.post(
    "/api/candidates/{candidate_id}/decision",
    response_model=CandidateDecisionResponse,
)
def decide_candidate(
    candidate_id: str,
    payload: CandidateDecisionRequest,
) -> CandidateDecisionResponse:
    session = session_store.get_session()
    if session.shortlist is None or not session.candidates or not session.scorecards:
        raise HTTPException(status_code=400, detail="Create ranking before decisions")
    if candidate_id not in session.candidates:
        raise HTTPException(status_code=404, detail="Candidate not found in session")

    existing_decision = session.decisions.get(candidate_id)
    if existing_decision and existing_decision != payload.decision:
        raise HTTPException(
            status_code=409,
            detail="Candidate already has a paused decision in the current session.",
        )
    if existing_decision == payload.decision:
        existing_draft = session.drafts.get(candidate_id)
        existing_no_availability = session.no_availability.get(candidate_id, False)
        if existing_draft is not None or existing_no_availability:
            proposed_slots = None
            if payload.decision == "invite":
                proposed_slots = ProposedSlots(
                    candidate_id=candidate_id,
                    slots=existing_draft.proposed_slots if existing_draft else [],
                )
            return CandidateDecisionResponse(
                candidate_id=candidate_id,
                decision=payload.decision,
                thread_id=thread_id_for(candidate_id),
                draft_email=existing_draft,
                proposed_slots=proposed_slots,
                no_availability=existing_no_availability,
            )

    graph_state = PipelineState(
        raw_jd_text=session.raw_jd_text,
        parsed_jd=session.parsed_jd,
        retrieved_rubric=session.retrieved_rubric,
        candidate_inputs=session.candidate_inputs,
        candidates=session.candidates,
        scorecards=session.scorecards,
        shortlist=session.shortlist,
        active_candidate_id=candidate_id,
        hr_decision=payload.decision,
        held_slots=session.held_slots,
    )

    try:
        result_state, _interrupt_value = run_outreach_until_interrupt(state=graph_state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session.decisions[candidate_id] = payload.decision
    session.no_availability[candidate_id] = result_state.no_availability

    if result_state.draft_email is not None:
        session.drafts[candidate_id] = result_state.draft_email
    session_store.save_session(session)

    return CandidateDecisionResponse(
        candidate_id=candidate_id,
        decision=payload.decision,
        thread_id=thread_id_for(candidate_id),
        draft_email=result_state.draft_email,
        proposed_slots=result_state.proposed_slots,
        no_availability=result_state.no_availability,
    )


@app.post(
    "/api/candidates/{candidate_id}/approve",
    response_model=ApproveDraftResponse,
)
def approve_candidate_draft(
    candidate_id: str,
    payload: ApproveDraftRequest,
) -> ApproveDraftResponse:
    session = session_store.get_session()
    if candidate_id not in session.candidates:
        raise HTTPException(status_code=404, detail="Candidate not found in session")
    if session.no_availability.get(candidate_id):
        raise HTTPException(status_code=400, detail="No draft exists because no slots were available")

    draft = session.drafts.get(candidate_id)
    if draft is None:
        raise HTTPException(status_code=400, detail="Create a draft decision before approval")
    if draft.status == "sent":
        return ApproveDraftResponse(
            candidate_id=candidate_id,
            thread_id=thread_id_for(candidate_id),
            draft_email=draft,
            held_slots=session.held_slots,
        )

    subject = payload.subject if payload.subject is not None else draft.subject
    body = payload.body if payload.body is not None else draft.body

    if not subject.strip():
        raise HTTPException(status_code=400, detail="Approved subject cannot be empty")
    if not body.strip():
        raise HTTPException(status_code=400, detail="Approved body cannot be empty")

    try:
        result_state = resume_outreach_after_approval(
            candidate_id=candidate_id,
            subject=subject,
            body=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result_state.draft_email is None or result_state.draft_email.status != "sent":
        raise HTTPException(status_code=500, detail="Approval did not produce a sent draft")

    session.drafts[candidate_id] = result_state.draft_email
    session.held_slots = result_state.held_slots
    session_store.save_session(session)

    return ApproveDraftResponse(
        candidate_id=candidate_id,
        thread_id=thread_id_for(candidate_id),
        draft_email=result_state.draft_email,
        held_slots=session.held_slots,
    )


@app.post("/api/rubrics/query", response_model=RetrievedRubric)
def query_rubrics_debug(
    q: str = Query(..., min_length=1),
    top_k: int = Query(8, ge=1, le=20),
) -> RetrievedRubric:
    try:
        return query_rubrics(q, top_k=top_k)
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/debug/parse-jd", response_model=ParsedJD)
def parse_jd_debug(payload: ParseJDRequest) -> ParsedJD:
    try:
        return parse_jd(payload.raw_jd_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/debug/parse-resume-text", response_model=CandidateProfile)
def parse_resume_text_debug(
    payload: ParseResumeTextRequest,
    use_llm: bool = Query(True),
) -> CandidateProfile:
    try:
        return parse_resume(
            CandidateInput(
                candidate_id=payload.candidate_id,
                raw_resume_text=payload.raw_resume_text,
            ),
            use_llm=use_llm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/debug/parse-resume-file", response_model=CandidateProfile)
def parse_resume_file_debug(
    payload: ParseResumeFileRequest,
    use_llm: bool = Query(True),
) -> CandidateProfile:
    try:
        return parse_resume_file(
            candidate_id=payload.candidate_id,
            resume_file=payload.resume_file,
            use_llm=use_llm,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
