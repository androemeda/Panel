"""Ingest rubric chunks into Pinecone."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.vectordb import DEFAULT_RUBRICS_PATH, ingest_rubrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest rubric chunks into Pinecone.")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_RUBRICS_PATH,
        help="Path to rubrics.json",
    )
    args = parser.parse_args()

    count = ingest_rubrics(args.path)
    print(f"Ingested {count} rubric chunks into Pinecone.")


if __name__ == "__main__":
    main()
