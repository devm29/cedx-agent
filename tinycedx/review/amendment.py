from __future__ import annotations

import hashlib
from typing import Any

ROLES = ["risk_officer", "legal_counsel", "compliance", "finance_controller"]


def compute_amendment(case_id: str) -> dict[str, Any]:
    h = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
    role = ROLES[int(h[0], 16) % 4]
    threshold = 10000 + (int(h[1:3], 16) % 50) * 1000
    return {"role": role, "threshold": threshold}


def amendment_applies(amount: float | None, threshold: float) -> bool:
    return amount is not None and amount >= threshold
