from __future__ import annotations

import re

_PATTERNS = [
    r"ignore\s+(all\s+)?(the\s+|your\s+)?(previous|prior|above|all)?\s*(instructions|rules|guidance)",
    r"disregard\s+(your|the|all|any|prior|previous)?\s*(rules|instructions|policy|guidance|guidelines)",
    r"override\s+(your|the)\s+(rules|policy|instructions)",
    r"approve\s+(this\s+)?(immediately|now|right away|without review)",
    r"(pre-?approved|mark(ed)?\s+as\s+approved)\b[^.]{0,40}\bwithout\s+(further\s+)?(review|check|checks|verification)",
    r"without\s+(further\s+)?(review|checks?|verification)\b",
    r"skip\s+(the\s+)?review",
    r"output\s+(only\s+)?approved\b",
    r"you\s+are\s+now\b",
    r"do\s+not\s+(flag|review|check|verify)\s+this",
    r"act\s+as\s+(if|though)\s+you\s+(are|were)\s+authorized",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def check_injection(notes: str | None) -> bool:
    if not notes:
        return False
    return any(p.search(notes) for p in _COMPILED)
