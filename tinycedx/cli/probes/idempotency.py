from __future__ import annotations

import json
import subprocess
import sys

from tinycedx import config


def _run_demo() -> dict:
    subprocess.run([sys.executable, "-m", "tinycedx.pipeline.run"], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return json.loads((config.OUT_DIR / "audit.json").read_text(encoding="utf-8"))


def _record_fingerprint(r: dict) -> tuple:
    return (r["id"], r["version"], r["status"], r["reason_code"], r.get("delivered_fields_hash"))


def main() -> int:
    print("  run 1/2 ...")
    audit1 = _run_demo()
    print("  run 2/2 ...")
    audit2 = _run_demo()

    failures: list[str] = []

    keys1 = [(r["id"], r["version"]) for r in audit1["records"]]
    keys2 = [(r["id"], r["version"]) for r in audit2["records"]]
    if len(keys1) != len(set(keys1)):
        failures.append(f"run 1 already has duplicate (id, version) records: {[k for k in keys1 if keys1.count(k) > 1]}")
    if len(keys2) != len(set(keys2)):
        failures.append(f"run 2 has duplicate (id, version) records: {[k for k in keys2 if keys2.count(k) > 1]}")
    if len(audit1["records"]) != len(audit2["records"]):
        failures.append(f"record count changed between runs: {len(audit1['records'])} -> {len(audit2['records'])}")
    if len(audit1["events"]) != len(audit2["events"]):
        failures.append(f"event count grew between runs: {len(audit1['events'])} -> {len(audit2['events'])} "
                         f"(events are accumulating instead of rebuilding)")

    fp1 = sorted(_record_fingerprint(r) for r in audit1["records"])
    fp2 = sorted(_record_fingerprint(r) for r in audit2["records"])
    if fp1 != fp2:
        failures.append("record content (status/reason_code/delivered_fields_hash) differs between runs")

    print(f"  run1: {len(audit1['records'])} records, {len(audit1['events'])} events")
    print(f"  run2: {len(audit2['records'])} records, {len(audit2['events'])} events")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("PASS: running demo twice produces identical record/event counts and content -- no duplicates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
