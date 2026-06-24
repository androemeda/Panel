"""JD parser node."""

from __future__ import annotations

import re

from ..schemas import JDRequirement, ParsedJD


SECTION_HEADERS = {
    "about": re.compile(r"^about\b", re.IGNORECASE),
    "responsibilities": re.compile(r"^responsibilit", re.IGNORECASE),
    "required": re.compile(r"^(requirements|required|qualifications).*(required)?", re.IGNORECASE),
    "preferred": re.compile(r"^(preferred|nice to have)", re.IGNORECASE),
}

ROLE_FAMILIES = [
    ("backend engineer", re.compile(r"\bbackend\b|\bserver\b|\bapi\b", re.IGNORECASE)),
    ("frontend engineer", re.compile(r"\bfrontend\b|\bfront-end\b|\breact\b|\bui\b", re.IGNORECASE)),
    ("devops engineer", re.compile(r"\bdevops\b|\binfrastructure\b|\bsre\b", re.IGNORECASE)),
    ("product manager", re.compile(r"\bproduct manager\b|\bproduct\b", re.IGNORECASE)),
]

SENIORITY_PATTERNS = [
    ("intern", re.compile(r"\bintern(ship)?\b", re.IGNORECASE)),
    ("junior", re.compile(r"\bjunior\b|\bentry[- ]level\b", re.IGNORECASE)),
    ("senior", re.compile(r"\bsenior\b|\bstaff\b|\bprincipal\b|\blead\b", re.IGNORECASE)),
    ("mid", re.compile(r"\bmid[- ]level\b|\bmid\b", re.IGNORECASE)),
]


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clean_bullet(line: str) -> str:
    line = re.sub(r"^\s*[-*]\s*", "", line)
    line = re.sub(r"^\s*\d+[.)]\s*", "", line)
    return line.strip()


def _is_section_header(line: str) -> bool:
    clean = _clean_bullet(line).rstrip(":")
    return any(pattern.search(clean) for pattern in SECTION_HEADERS.values())


def _section_for_line(line: str) -> str | None:
    clean = _clean_bullet(line).rstrip(":")
    for name, pattern in SECTION_HEADERS.items():
        if pattern.search(clean):
            return name
    return None


def _collect_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "responsibilities": [],
        "required": [],
        "preferred": [],
    }
    active: str | None = None

    for line in lines[1:]:
        header = _section_for_line(line)
        if header:
            active = header if header in sections else None
            continue

        if active in sections:
            clean = _clean_bullet(line)
            if clean and not _is_section_header(clean):
                sections[active].append(clean)

    return sections


def _detect_role_family(title: str, text: str) -> str:
    for role_family, pattern in ROLE_FAMILIES:
        if pattern.search(title):
            return role_family

    haystack = f"{title}\n{text}"
    for role_family, pattern in ROLE_FAMILIES:
        if pattern.search(haystack):
            return role_family
    return title.lower().strip() or "general"


def _detect_seniority(title: str, text: str) -> str:
    haystack = f"{title}\n{text}"
    for seniority, pattern in SENIORITY_PATTERNS:
        if pattern.search(haystack):
            return seniority
    return "mid"


def _requirements_from_lines(
    required_lines: list[str], preferred_lines: list[str]
) -> list[JDRequirement]:
    requirements: list[JDRequirement] = []
    for line in required_lines:
        requirements.append(JDRequirement(skill=line, importance="required"))
    for line in preferred_lines:
        requirements.append(JDRequirement(skill=line, importance="preferred"))
    return requirements


def _build_retrieval_query(
    role_title: str,
    role_family: str,
    seniority: str,
    requirements: list[JDRequirement],
    responsibilities: list[str],
) -> str:
    required_terms = " ".join(
        requirement.skill for requirement in requirements if requirement.importance == "required"
    )
    responsibility_terms = " ".join(responsibilities[:3])
    return " ".join(
        part
        for part in [
            seniority,
            role_family,
            role_title,
            required_terms,
            responsibility_terms,
        ]
        if part
    )


def parse_jd(raw_jd_text: str) -> ParsedJD:
    lines = _non_empty_lines(raw_jd_text)
    if not lines:
        raise ValueError("JD text cannot be empty")

    role_title = _clean_bullet(lines[0]).rstrip(":")
    sections = _collect_sections(lines)
    role_family = _detect_role_family(role_title, raw_jd_text)
    seniority = _detect_seniority(role_title, raw_jd_text)
    requirements = _requirements_from_lines(
        sections["required"], sections["preferred"]
    )
    responsibilities = sections["responsibilities"]
    retrieval_query = _build_retrieval_query(
        role_title,
        role_family,
        seniority,
        requirements,
        responsibilities,
    )

    return ParsedJD(
        role_title=role_title,
        role_family=role_family,
        seniority=seniority,  # type: ignore[arg-type]
        required_skills=requirements,
        responsibilities=responsibilities,
        retrieval_query=retrieval_query,
    )
