from __future__ import annotations

import statistics
from typing import Any

from tinycedx.config import OUTLIER_MODIFIED_Z_THRESHOLD


def compute_outliers(records: list[dict[str, Any]]) -> set[str]:
    pairs = [(r["id"], r["amount"]) for r in records if isinstance(r.get("amount"), (int, float))]
    values = [v for _, v in pairs]
    if len(values) < 3:
        return set()

    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)

    if mad == 0:
        s = sorted(values)
        mid = len(s) // 2
        q1 = statistics.median(s[:mid])
        q3 = statistics.median(s[mid + (len(s) % 2):])
        iqr = q3 - q1
        if iqr == 0:
            return set()
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        return {rid for rid, v in pairs if v < lo or v > hi}

    outliers = set()
    for rid, v in pairs:
        modified_z = 0.6745 * (v - median) / mad
        if abs(modified_z) > OUTLIER_MODIFIED_Z_THRESHOLD:
            outliers.add(rid)
    return outliers
