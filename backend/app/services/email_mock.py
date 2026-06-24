"""Email delivery service."""

from __future__ import annotations

import html
import json
from pathlib import Path
from threading import Lock
from urllib import error, request

from ..config import BACKEND_ROOT, get_settings
from ..schemas import DraftEmail


SENT_EMAILS_PATH = BACKEND_ROOT / ".local" / "sent_emails.json"
RESEND_API_URL = "https://api.resend.com/emails"
_LOCK = Lock()


class EmailConfigurationError(RuntimeError):
    """Raised when real email delivery is not configured."""


class EmailDeliveryError(RuntimeError):
    """Raised when Resend rejects or fails an email request."""


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


def _body_to_html(body: str) -> str:
    escaped = html.escape(body).replace("\n", "<br>")
    return (
        "<!doctype html>"
        "<html><body>"
        f"<div style=\"font-family:Arial,sans-serif;line-height:1.5;color:#111827\">{escaped}</div>"
        "</body></html>"
    )


def _resend_error_message(payload: bytes) -> str:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace") or "Resend request failed"

    if isinstance(decoded, dict):
        message = decoded.get("message")
        if isinstance(message, str) and message:
            return message
        error_value = decoded.get("error")
        if isinstance(error_value, str) and error_value:
            return error_value
        if isinstance(error_value, dict):
            nested = error_value.get("message")
            if isinstance(nested, str) and nested:
                return nested
    return "Resend request failed"


def _send_via_resend(draft_email: DraftEmail) -> dict:
    settings = get_settings()
    if not settings.resend_api_key:
        raise EmailConfigurationError("RESEND_API_KEY is not configured")

    payload = {
        "from": settings.resend_from_email,
        "to": [draft_email.to],
        "subject": draft_email.subject,
        "html": _body_to_html(draft_email.body),
    }
    data = json.dumps(payload).encode("utf-8")
    resend_request = request.Request(
        RESEND_API_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "recruiting-screening-pipeline/0.1",
        },
    )

    try:
        with request.urlopen(resend_request, timeout=30) as response:
            response_body = response.read()
            if not response_body:
                return {}
            return json.loads(response_body.decode("utf-8"))
    except error.HTTPError as exc:
        raise EmailDeliveryError(_resend_error_message(exc.read())) from exc
    except error.URLError as exc:
        raise EmailDeliveryError(f"Could not reach Resend: {exc.reason}") from exc
    except TimeoutError as exc:
        raise EmailDeliveryError("Timed out while sending email through Resend") from exc
    except json.JSONDecodeError as exc:
        raise EmailDeliveryError("Resend returned an invalid JSON response") from exc


def send_email(draft_email: DraftEmail) -> DraftEmail:
    _send_via_resend(draft_email)
    sent_email = draft_email.model_copy(update={"status": "sent"})
    with _LOCK:
        emails = _read_sent()
        emails.append(sent_email)
        _write_sent(emails)
    return sent_email


def list_sent_emails() -> list[DraftEmail]:
    with _LOCK:
        return _read_sent()
