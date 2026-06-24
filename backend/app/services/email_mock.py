"""Mock email service."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from ..config import BACKEND_ROOT
from ..schemas import DraftEmail


SENT_EMAILS_PATH = BACKEND_ROOT / ".local" / "sent_emails.json"
_LOCK = Lock()


def _read_sent(path: Path = SENT_EMAILS_PATH) -> list[DraftEmail]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [DraftEmail.model_validate(item) for item in raw]


def _write_sent(emails: list[DraftEmail], path: Path = SENT_EMAILS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([email.model_dump(mode="json") for email in emails], indent=2),
        encoding="utf-8",
    )


def send_email(draft_email: DraftEmail) -> DraftEmail:
    sent_email = draft_email.model_copy(update={"status": "sent"})
    with _LOCK:
        emails = _read_sent()
        emails.append(sent_email)
        _write_sent(emails)
    return sent_email


def list_sent_emails() -> list[DraftEmail]:
    with _LOCK:
        return _read_sent()
