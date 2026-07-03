from __future__ import annotations

from datetime import date
from typing import Any

from tinycedx.detectors.injection import check_injection
from tinycedx.detectors.low_confidence import prefilter_low_confidence
from tinycedx.detectors.missing import check_missing
from tinycedx.detectors.outlier import compute_outliers
from tinycedx.detectors.stale import check_stale
from tinycedx.detectors.unverified import check_unverified_anomaly


def classify_batch(records: list[dict[str, Any]], pipeline_now: date) -> dict[str, dict[str, Any]]:
    outlier_ids = compute_outliers(records)
    verdicts: dict[str, dict[str, Any]] = {}

    for r in records:
        rid = r["id"]

        if check_stale(r, pipeline_now):
            verdicts[rid] = {
                "reason_code": "STALE", "reason_class": "A", "low_confidence_flag": False,
                "detail": f"deadline {r.get('deadline')} is before PIPELINE_NOW {pipeline_now.isoformat()}",
            }
            continue

        missing = check_missing(r)
        if missing:
            verdicts[rid] = {
                "reason_code": "MISSING_INPUT", "reason_class": "A", "low_confidence_flag": False,
                "detail": f"required field(s) missing: {missing}",
            }
            continue

        if rid in outlier_ids:
            verdicts[rid] = {
                "reason_code": "OUTLIER", "reason_class": "A", "low_confidence_flag": False,
                "detail": "amount is a robust-statistic (median/MAD modified z-score) outlier vs. this batch",
            }
            continue

        if check_injection(r.get("notes")):
            verdicts[rid] = {
                "reason_code": "INJECTION_BLOCKED", "reason_class": "A", "low_confidence_flag": False,
                "detail": "notes contain instruction-override language",
            }
            continue

        if check_unverified_anomaly(r):
            verdicts[rid] = {
                "reason_code": "UNVERIFIED_ANOMALY", "reason_class": "A", "low_confidence_flag": False,
                "detail": "record fails a generic validation rule matched by no named detector",
            }
            continue

        verdicts[rid] = {
            "reason_code": None, "reason_class": None,
            "low_confidence_flag": prefilter_low_confidence(r),
            "detail": None,
        }

    return verdicts
