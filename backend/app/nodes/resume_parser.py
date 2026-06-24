"""Resume parser node."""

from __future__ import annotations

from io import BytesIO
import re
from pathlib import Path

from pydantic import BaseModel, Field
from pypdf import PdfReader

from ..config import BACKEND_ROOT, get_settings
from ..llm import get_llm
from ..schemas import CandidateInput, CandidateProfile, WorkExperience


DATA_ROOT = BACKEND_ROOT / "data"
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(\+\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
URL_PATTERN = re.compile(r"https?://|linkedin\.com|github\.com", re.IGNORECASE)

COMMON_SKILLS = [
    ("Python", r"\bpython\b"),
    ("Go", r"\bgolang\b|\bgo\b"),
    ("Java", r"\bjava\b"),
    ("JavaScript", r"\bjavascript\b|\bjs\b"),
    ("TypeScript", r"\btypescript\b|\bts\b"),
    ("React", r"\breact\b"),
    ("Node.js", r"\bnode\.?js\b|\bnode\b"),
    ("FastAPI", r"\bfastapi\b"),
    ("Django", r"\bdjango\b"),
    ("SQL", r"\bsql\b"),
    ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
    ("MySQL", r"\bmysql\b"),
    ("MongoDB", r"\bmongodb\b"),
    ("Redis", r"\bredis\b"),
    ("Kafka", r"\bkafka\b"),
    ("RabbitMQ", r"\brabbitmq\b"),
    ("AWS", r"\baws\b|amazon web services"),
    ("GCP", r"\bgcp\b|google cloud"),
    ("Azure", r"\bazure\b"),
    ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("Terraform", r"\bterraform\b"),
    ("CI/CD", r"\bci/cd\b|\bcontinuous integration\b"),
    ("System Design", r"\bsystem design\b"),
    ("Distributed Systems", r"\bdistributed systems?\b"),
    ("Observability", r"\bobservability\b|\bmonitoring\b|\btracing\b"),
    ("Product Strategy", r"\bproduct strategy\b|\broadmap\b"),
    ("Analytics", r"\banalytics\b|\bmetrics\b"),
]

EDUCATION_PATTERN = re.compile(
    r"\b(bachelor|master|ph\.?d|b\.?tech|m\.?tech|b\.?s\.?|m\.?s\.?|mba|university|college|institute)\b",
    re.IGNORECASE,
)


class _ResumeFields(BaseModel):
    name: str = ""
    email: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[WorkExperience] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)


def extract_resume_text(path: Path | str) -> str:
    resume_path = Path(path)
    if not resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_path}")

    suffix = resume_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(resume_path))
        page_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(page_text).strip()

    if suffix in {".txt", ".md"}:
        return resume_path.read_text(encoding="utf-8").strip()

    raise ValueError(f"Unsupported resume file type: {suffix or '<none>'}")


def extract_resume_text_from_bytes(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        raise ValueError("Only PDF resume uploads are supported")

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise ValueError(f"Could not read PDF upload: {filename}") from exc

    page_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(page_text).strip()


def resolve_resume_file(resume_file: str) -> Path:
    candidate_path = (DATA_ROOT / resume_file).resolve()
    data_root = DATA_ROOT.resolve()
    if data_root not in candidate_path.parents and candidate_path != data_root:
        raise ValueError("Resume file must live under backend/data")
    return candidate_path


def _extract_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else None


def _guess_name(text: str) -> str | None:
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if EMAIL_PATTERN.search(clean) or PHONE_PATTERN.search(clean) or URL_PATTERN.search(clean):
            continue
        if clean.lower() in {"resume", "curriculum vitae", "cv"}:
            continue
        if len(clean) <= 80 and re.search(r"[A-Za-z]", clean):
            return clean
    return None


def _extract_skills(text: str) -> list[str]:
    skills: list[str] = []
    for label, pattern in COMMON_SKILLS:
        if re.search(pattern, text, re.IGNORECASE):
            skills.append(label)
    return skills


def _extract_education(text: str) -> list[str]:
    education: list[str] = []
    for line in text.splitlines():
        clean = line.strip(" -\t")
        if clean and EDUCATION_PATTERN.search(clean):
            education.append(clean)
    return education[:5]


def _fallback_fields(candidate_input: CandidateInput) -> _ResumeFields:
    text = candidate_input.raw_resume_text
    return _ResumeFields(
        name=_guess_name(text) or candidate_input.candidate_id,
        email=_extract_email(text) or f"{candidate_input.candidate_id}@example.test",
        skills=_extract_skills(text),
        experience=[],
        education=_extract_education(text),
    )


def _llm_extract_fields(candidate_input: CandidateInput) -> _ResumeFields:
    structured_llm = get_llm().with_structured_output(_ResumeFields)
    fallback = _fallback_fields(candidate_input)
    prompt = (
        "Extract job-relevant resume facts from the text. Use only information present "
        "in the resume. For duration_months, estimate from explicit dates when possible; "
        "use 0 if dates are not available. If name or email is missing, use the provided "
        "fallback values.\n\n"
        f"Candidate ID: {candidate_input.candidate_id}\n"
        f"Fallback name: {fallback.name}\n"
        f"Fallback email: {fallback.email}\n\n"
        f"Resume text:\n{candidate_input.raw_resume_text}"
    )
    result = structured_llm.invoke(
        [
            (
                "system",
                "You are a precise resume extraction node. Return structured facts only.",
            ),
            ("human", prompt),
        ]
    )
    if isinstance(result, _ResumeFields):
        return result
    return _ResumeFields.model_validate(result)


def parse_resume(candidate_input: CandidateInput, use_llm: bool = True) -> CandidateProfile:
    if not candidate_input.raw_resume_text.strip():
        raise ValueError("Resume text cannot be empty")

    fallback = _fallback_fields(candidate_input)
    fields = fallback

    if use_llm and get_settings().openai_api_key:
        try:
            fields = _llm_extract_fields(candidate_input)
        except Exception:
            fields = fallback

    email = _extract_email(candidate_input.raw_resume_text) or fields.email or fallback.email
    name = fields.name.strip() or fallback.name

    return CandidateProfile(
        candidate_id=candidate_input.candidate_id,
        name=name,
        email=email,
        skills=fields.skills or fallback.skills,
        experience=fields.experience,
        education=fields.education or fallback.education,
        raw_text=candidate_input.raw_resume_text,
    )


def parse_resume_file(candidate_id: str, resume_file: str, use_llm: bool = True) -> CandidateProfile:
    resume_path = resolve_resume_file(resume_file)
    raw_resume_text = extract_resume_text(resume_path)
    return parse_resume(
        CandidateInput(candidate_id=candidate_id, raw_resume_text=raw_resume_text),
        use_llm=use_llm,
    )
