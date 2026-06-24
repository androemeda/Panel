"""Ranking agent."""

from __future__ import annotations

import json

from ..llm import get_llm
from ..schemas import CandidateProfile, ParsedJD, Scorecard, Shortlist


def rank_candidates(
    parsed_jd: ParsedJD,
    candidates: dict[str, CandidateProfile],
    scorecards: dict[str, Scorecard],
) -> Shortlist:
    structured_llm = get_llm().with_structured_output(Shortlist)
    prompt_payload = {
        "parsed_jd": parsed_jd.model_dump(),
        "candidates": {
            candidate_id: profile.model_dump()
            for candidate_id, profile in candidates.items()
        },
        "scorecards": {
            candidate_id: scorecard.model_dump()
            for candidate_id, scorecard in scorecards.items()
        },
    }

    result = structured_llm.invoke(
        [
            (
                "system",
                (
                    "You are the Ranking Agent. Produce a comparative ranked shortlist "
                    "for the whole candidate pool. Use the scorecards and raw candidate "
                    "profiles to break ties. Keep reasoning job-relevant, specific, and "
                    "comparative. Include every candidate exactly once."
                ),
            ),
            (
                "human",
                "Return a valid Shortlist for this pool:\n"
                f"{json.dumps(prompt_payload, indent=2, default=str)}",
            ),
        ]
    )

    shortlist = result if isinstance(result, Shortlist) else Shortlist.model_validate(result)
    candidate_ids = set(candidates)
    ranked_ids = {candidate.candidate_id for candidate in shortlist.ranked_candidates}
    if ranked_ids != candidate_ids:
        missing = candidate_ids - ranked_ids
        extra = ranked_ids - candidate_ids
        raise ValueError(
            f"Shortlist candidate ids did not match pool. Missing={missing}; extra={extra}"
        )
    return shortlist
