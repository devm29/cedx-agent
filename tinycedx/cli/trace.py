from __future__ import annotations

import argparse
import json
import sys

from tinycedx import config


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

    print(f"record {r['id']}  status={r['status']}  reason_code={r['reason_code']}  "
          f"reason_class={r['reason_class']}")
    if r.get("detail"):
        print(f"  detail: {r['detail']}")
    print(f"  source_format={r['source_format']}  version={r.get('version')}  "
          f"source_version_hash={r.get('source_version_hash')}")
    print()
    print(f"agent_trace ({len(r['agent_trace'])} span(s)):")
    for i, span in enumerate(r["agent_trace"], 1):
        parts = [f"[{i}] agent={span['agent']:<12} status={span['status']:<10}"]
        if span.get("verdict"):
            parts.append(f"verdict={span['verdict']}")
        if span.get("model"):
            parts.append(f"model={span['model']}")
        if span.get("cost_usd") is not None:
            parts.append(f"cost=${span['cost_usd']:.6f}")
        if span.get("latency_ms") is not None:
            parts.append(f"latency={span['latency_ms']:.0f}ms")
        if span.get("tokens_in") is not None:
            parts.append(f"tokens={span['tokens_in']}in/{span['tokens_out']}out")
        if span.get("retries") is not None:
            parts.append(f"retries={span['retries']}")
        if span.get("transcript_hash"):
            parts.append(f"transcript={span['transcript_hash'][:19]}...")
        print("  " + "  ".join(parts))

    print()
    print(f"approval_trail ({len(r['approval_trail'])} entr{'y' if len(r['approval_trail'])==1 else 'ies'}):")
    for e in r["approval_trail"]:
        role = f" role={e['role']}" if e.get("role") else ""
        print(f"  state={e['state']:<18} actor={e['actor']:<28} ts={e['ts']}{role}")

    if r.get("delivered_fields"):
        print()
        print("delivered_fields:")
        print(json.dumps(r["delivered_fields"], indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
