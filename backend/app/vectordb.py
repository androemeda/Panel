"""Pinecone vector database helpers.

Phase 1 implements rubric ingestion/query helpers here.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from .config import BACKEND_ROOT, get_settings
from .llm import get_embeddings
from .schemas import RetrievedRubric, RubricChunk


RUBRIC_NAMESPACE = "rubrics"
EMBEDDING_DIMENSION = 1536
DEFAULT_TOP_K = 8
DEFAULT_RUBRICS_PATH = BACKEND_ROOT / "data" / "rubrics.json"


class MissingConfigurationError(RuntimeError):
    """Raised when a required API key or service setting is not configured."""


def require_vector_settings() -> None:
    settings = get_settings()
    missing = []

    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.pinecone_api_key:
        missing.append("PINECONE_API_KEY")
    if not settings.pinecone_index_name:
        missing.append("PINECONE_INDEX_NAME")

    if missing:
        joined = ", ".join(missing)
        raise MissingConfigurationError(f"Missing required environment values: {joined}")


def rubric_embedding_text(chunk: RubricChunk) -> str:
    return (
        f"{chunk.seniority} {chunk.role_family} - {chunk.competency}: "
        f"{chunk.strong_descriptor}"
    )


def deterministic_rubric_id(chunk: RubricChunk) -> str:
    return f"{chunk.role_family}|{chunk.seniority}|{chunk.competency}"


def load_rubric_chunks(path: Path | str = DEFAULT_RUBRICS_PATH) -> list[RubricChunk]:
    rubric_path = Path(path)
    with rubric_path.open("r", encoding="utf-8") as file:
        raw_chunks = json.load(file)

    if not isinstance(raw_chunks, list):
        raise ValueError(f"Expected a JSON array in {rubric_path}")

    return [RubricChunk.model_validate(chunk) for chunk in raw_chunks]


def get_pinecone_client() -> Pinecone:
    require_vector_settings()
    settings = get_settings()
    return Pinecone(api_key=settings.pinecone_api_key)


def get_pinecone_index():
    settings = get_settings()
    client = get_pinecone_client()
    return client.Index(settings.pinecone_index_name)


def ensure_rubric_index() -> None:
    settings = get_settings()
    client = get_pinecone_client()

    if client.has_index(settings.pinecone_index_name):
        return

    client.create_index(
        name=settings.pinecone_index_name,
        dimension=EMBEDDING_DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=settings.pinecone_cloud,
            region=settings.pinecone_region,
        ),
    )

    while True:
        description = client.describe_index(settings.pinecone_index_name)
        status = getattr(description, "status", None)
        ready = status.get("ready") if isinstance(status, dict) else getattr(status, "ready", False)
        if ready:
            return
        time.sleep(2)


def _metadata_from_chunk(chunk: RubricChunk) -> dict[str, Any]:
    payload = chunk.model_dump(exclude={"score"})
    return payload


def _chunk_from_metadata(metadata: dict[str, Any], score: float | None = None) -> RubricChunk:
    return RubricChunk.model_validate({**metadata, "score": score})


def ingest_rubrics(path: Path | str = DEFAULT_RUBRICS_PATH, batch_size: int = 50) -> int:
    chunks = load_rubric_chunks(path)
    ensure_rubric_index()

    embeddings = get_embeddings()
    index = get_pinecone_index()
    namespace = get_settings().pinecone_namespace or RUBRIC_NAMESPACE

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [rubric_embedding_text(chunk) for chunk in batch]
        vectors = embeddings.embed_documents(texts)
        index.upsert(
            vectors=[
                {
                    "id": deterministic_rubric_id(chunk),
                    "values": vector,
                    "metadata": _metadata_from_chunk(chunk),
                }
                for chunk, vector in zip(batch, vectors, strict=True)
            ],
            namespace=namespace,
        )

    return len(chunks)


def query_rubrics(query: str, top_k: int = DEFAULT_TOP_K) -> RetrievedRubric:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Query cannot be empty")

    require_vector_settings()

    vector = get_embeddings().embed_query(clean_query)
    index = get_pinecone_index()
    namespace = get_settings().pinecone_namespace or RUBRIC_NAMESPACE
    result = index.query(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )

    chunks = [
        _chunk_from_metadata(match.metadata or {}, score=match.score)
        for match in result.matches
    ]
    return RetrievedRubric(chunks=chunks, query_used=clean_query)
