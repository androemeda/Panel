"""Rubric retriever node."""

from __future__ import annotations

from ..schemas import ParsedJD, RetrievedRubric
from ..vectordb import DEFAULT_TOP_K, query_rubrics


def retrieve_rubric(parsed_jd: ParsedJD, top_k: int = DEFAULT_TOP_K) -> RetrievedRubric:
    return query_rubrics(parsed_jd.retrieval_query, top_k=top_k)
