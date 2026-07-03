from __future__ import annotations

from typing import Any


def summarize_cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0.0
    latencies: list[float] = []
    for r in records:
        for span in r.get("agent_trace", []) or []:
            c = span.get("cost_usd")
            if isinstance(c, (int, float)):
                total += c
            lat = span.get("latency_ms")
            if isinstance(lat, (int, float)):
                latencies.append(lat)

    n = len(records)
    avg = total / n if n else 0.0

    p95 = 0.0
    if latencies:
        s = sorted(latencies)
        idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
        p95 = s[idx]

    return {
        "total_usd": round(total, 6),
        "avg_usd_per_record": round(avg, 6),
        "p95_latency_ms": round(p95, 3),
        "records": n,
        "projected_usd_per_10k": round(avg * 10000, 2),
    }
