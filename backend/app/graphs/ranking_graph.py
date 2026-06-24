"""Graph 1: JD parsing, rubric retrieval, screening, and ranking."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..nodes.jd_parser import parse_jd
from ..nodes.ranking_agent import rank_candidates
from ..nodes.resume_parser import parse_resume
from ..nodes.rubric_retriever import retrieve_rubric
from ..nodes.screening_agent import screen_candidate
from ..schemas import CandidateInput
from ..state import PipelineState


def _state(value: PipelineState | dict[str, Any]) -> PipelineState:
    if isinstance(value, PipelineState):
        return value
    return PipelineState.model_validate(value)


def jd_parser_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if not current.raw_jd_text:
        raise ValueError("raw_jd_text is required")
    return {"parsed_jd": parse_jd(current.raw_jd_text)}


def rubric_retriever_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.parsed_jd is None:
        raise ValueError("parsed_jd is required before rubric retrieval")
    return {"retrieved_rubric": retrieve_rubric(current.parsed_jd)}


def dispatch_candidates(state: PipelineState | dict[str, Any]) -> list[Send]:
    current = _state(state)
    if not current.candidate_inputs:
        raise ValueError("At least one candidate input is required")
    if current.parsed_jd is None or current.retrieved_rubric is None:
        raise ValueError("parsed_jd and retrieved_rubric are required before screening")

    return [
        Send(
            "screen_candidate",
            {
                "candidate_input": candidate_input,
                "parsed_jd": current.parsed_jd,
                "retrieved_rubric": current.retrieved_rubric,
            },
        )
        for candidate_input in current.candidate_inputs
    ]


def screen_candidate_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.candidate_input is None:
        raise ValueError("candidate_input is required for screening")
    if current.parsed_jd is None or current.retrieved_rubric is None:
        raise ValueError("parsed_jd and retrieved_rubric are required for screening")

    candidate_profile = parse_resume(current.candidate_input, use_llm=True)
    scorecard = screen_candidate(
        candidate=candidate_profile,
        parsed_jd=current.parsed_jd,
        retrieved_rubric=current.retrieved_rubric,
    )
    candidate_id = current.candidate_input.candidate_id
    return {
        "candidates": {candidate_id: candidate_profile},
        "scorecards": {candidate_id: scorecard},
    }


def ranking_agent_node(state: PipelineState | dict[str, Any]) -> dict[str, Any]:
    current = _state(state)
    if current.parsed_jd is None:
        raise ValueError("parsed_jd is required before ranking")
    if not current.candidates or not current.scorecards:
        raise ValueError("candidates and scorecards are required before ranking")

    expected_ids = {candidate.candidate_id for candidate in current.candidate_inputs}
    if expected_ids and set(current.scorecards) != expected_ids:
        missing = expected_ids - set(current.scorecards)
        raise ValueError(f"Missing scorecards for candidate ids: {sorted(missing)}")

    return {
        "shortlist": rank_candidates(
            parsed_jd=current.parsed_jd,
            candidates=current.candidates,
            scorecards=current.scorecards,
        )
    }


@lru_cache
def build_ranking_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("jd_parser", jd_parser_node)
    graph.add_node("rubric_retriever", rubric_retriever_node)
    graph.add_node("screen_candidate", screen_candidate_node)
    graph.add_node("ranking_agent", ranking_agent_node)

    graph.add_edge(START, "jd_parser")
    graph.add_edge("jd_parser", "rubric_retriever")
    graph.add_conditional_edges("rubric_retriever", dispatch_candidates, ["screen_candidate"])
    graph.add_edge("screen_candidate", "ranking_agent")
    graph.add_edge("ranking_agent", END)
    return graph.compile()


def run_ranking_graph(
    raw_jd_text: str,
    candidate_inputs: list[CandidateInput],
) -> PipelineState:
    graph = build_ranking_graph()
    initial_state = PipelineState(
        raw_jd_text=raw_jd_text,
        candidate_inputs=candidate_inputs,
    )
    config: dict[str, Any] = {
        "run_name": "ranking_graph",
    }
    result = graph.invoke(initial_state, config=config)
    return _state(result)
