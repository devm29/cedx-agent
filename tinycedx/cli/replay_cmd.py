from __future__ import annotations

import argparse
import json
import sys

from tinycedx import config
from tinycedx.hashutil import sha


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--audit", default=str(config.OUT_DIR / "audit.json"))
    args = ap.parse_args()

    try:
        audit = json.loads(open(args.audit, encoding="utf-8").read())
    except FileNotFoundError:
        print(f"FAIL: {args.audit} not found -- run `make demo` first", file=sys.stderr)
        return 1

    records = [r for r in audit["records"] if r["id"] == args.id]
    if not records:
        print(f"FAIL: no record {args.id!r} in {args.audit}", file=sys.stderr)
        return 1
    r = records[0]

    print(f"lineage for {r['id']}")
    print(f"  provenance: source_format={r['source_format']}  source_version_hash={r.get('source_version_hash')}")
    print(f"  final status: {r['status']}  reason_code={r['reason_code']}")

    events = [e for e in audit["events"] if e.get("record_id") == r["id"]]
    print(f"\n  {len(events)} audit event(s) for this record (append-only, seq order):")
    for e in events:
        print(f"    seq={e['seq']:<4} ts={e['ts']}  actor={e['actor']:<28} action={e['action']}")

    if r["status"] == "delivered":
        th = r.get("transcript_hash", "")
        stem = th.split(":")[-1] if th else None
        tpath = config.TRANSCRIPTS_DIR / f"{stem}.json" if stem else None
        print(f"\n  delivered_fields_hash: {r.get('delivered_fields_hash')}")
        print(f"  backed by transcript:  {th}")
        if tpath and tpath.exists():
            t = json.loads(tpath.read_text(encoding="utf-8"))
            print(f"    -> {tpath.name}: agent={t['agent']} model={t['model']} attempt={t['attempt']}")
            computed = sha(r["delivered_fields"])
            match = "OK" if computed == r.get("delivered_fields_hash") else "MISMATCH"
            print(f"    -> recomputed delivered_fields_hash matches audit entry: {match}")
        else:
            print("    -> WARNING: transcript file not found on disk")
    elif r["status"] == "superseded":
        print(f"\n  {r.get('detail')}")
    else:
        print(f"\n  never reached delivery: {r.get('detail')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
