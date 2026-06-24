"""Shared fixtures for the evaluation suite.

These tests run in-process with FastAPI's TestClient, so the backend server does
NOT need to be running. State that lives under ``backend/.local`` (session store,
sent-email log, outreach checkpoints) is wiped before and after every test so each
scenario starts from a clean slate and tests never interfere with each other.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``import app...`` work no matter where pytest is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.graphs import outreach_graph  # noqa: E402
from app.main import app  # noqa: E402
from app.services import email_mock  # noqa: E402
from app.services.store import session_store  # noqa: E402


# --- key-gated markers -------------------------------------------------------
_settings = get_settings()
HAS_OPENAI = bool(_settings.openai_api_key)
HAS_PINECONE = bool(_settings.pinecone_api_key)

requires_llm = pytest.mark.skipif(
    not HAS_OPENAI,
    reason="needs OPENAI_API_KEY (LLM scoring)",
)
requires_full_pipeline = pytest.mark.skipif(
    not (HAS_OPENAI and HAS_PINECONE),
    reason="needs OPENAI_API_KEY + PINECONE_API_KEY (full ranking graph)",
)


def _wipe_local_state() -> None:
    """Reset the single active session and all on-disk side effects."""
    session_store.clear_pool()

    if email_mock.SENT_EMAILS_PATH.exists():
        email_mock.SENT_EMAILS_PATH.unlink()

    # The compiled outreach graph caches a SqliteSaver bound to the checkpoint
    # file; drop the cache before removing the file so a fresh saver is built.
    outreach_graph.build_outreach_graph.cache_clear()
    if outreach_graph.CHECKPOINT_PATH.exists():
        outreach_graph.CHECKPOINT_PATH.unlink()


def _fake_send_email(draft_email):
    sent_email = draft_email.model_copy(update={"status": "sent"})
    emails = email_mock._read_sent()
    emails.append(sent_email)
    email_mock._write_sent(emails)
    return sent_email


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    _wipe_local_state()
    monkeypatch.setattr(outreach_graph, "send_email", _fake_send_email)
    yield
    _wipe_local_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def resume_pdfs() -> list[Path]:
    resume_dir = BACKEND_ROOT / "data" / "resumes"
    pdfs = sorted(resume_dir.glob("*.pdf"))
    if not pdfs:
        pytest.skip("no sample resume PDFs under backend/data/resumes")
    return pdfs
