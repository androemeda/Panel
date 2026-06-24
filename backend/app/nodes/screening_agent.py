"""Screening agent."""

from __future__ import annotations

import json

from ..llm import get_llm
from ..schemas import CandidateProfile, ParsedJD, RetrievedRubric, Scorecard


def screen_candidate(
    candidate: CandidateProfile,
    parsed_jd: ParsedJD,
    retrieved_rubric: RetrievedRubric,
) -> Scorecard:
    structured_llm = get_llm().with_structured_output(Scorecard)

    prompt_payload = {
        "candidate": candidate.model_dump(),
        "parsed_jd": parsed_jd.model_dump(),
        "retrieved_rubric": retrieved_rubric.model_dump(),
    }

    result = structured_llm.invoke(
        [
            (
                "system",
                (
                    "You are the Screening Agent for a recruiting pipeline. Score only "
                    "job-relevant competencies from the JD and retrieved rubric. Do not "
                    "use protected-class or demographic information. Each competency "
                    "score must cite concrete evidence from this resume. Required skills "
                    "should weigh more heavily in the overall_score. Use score 1-10."
                ),
            ),
            (
                "human",
                "Return a valid Scorecard for this candidate:\n"
                f"{json.dumps(prompt_payload, indent=2, default=str)}",
            ),
        ]
    )

    scorecard = result if isinstance(result, Scorecard) else Scorecard.model_validate(result)
    if scorecard.candidate_id != candidate.candidate_id:
        scorecard = scorecard.model_copy(update={"candidate_id": candidate.candidate_id})
    return scorecard
