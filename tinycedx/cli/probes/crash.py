from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

from tinycedx import config


def _audit_is_valid_or_absent() -> bool:
    path = config.OUT_DIR / "audit.json"
    if not path.exists():
        return True
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except json.JSONDecodeError:
        return False


def main() -> int:
    if (config.OUT_DIR / "audit.json").exists():
        (config.OUT_DIR / "audit.json").unlink()

    print("  starting pipeline, then SIGKILL-ing it mid-run ...")
    proc = subprocess.Popen([sys.executable, "-m", "tinycedx.pipeline.run"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.05)
    proc.send_signal(signal.SIGKILL)
    proc.wait()

    if not _audit_is_valid_or_absent():
        print("FAIL: out/audit.json is corrupt/truncated after the kill (atomic write was bypassed)")
        return 1
    print("  post-kill state OK: audit.json is either absent or a prior complete file")

    print("  re-running the pipeline from scratch ...")
    subprocess.run([sys.executable, "-m", "tinycedx.pipeline.run"], check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    audit = json.loads((config.OUT_DIR / "audit.json").read_text(encoding="utf-8"))
    keys = [(r["id"], r["version"]) for r in audit["records"]]
    dupes = [k for k in set(keys) if keys.count(k) > 1]
    if dupes:
        print(f"FAIL: re-run after crash produced duplicate (id, version) records: {dupes}")
        return 1

    verify = subprocess.run(
        [sys.executable, "verify_audit.py", "--audit", "out/audit.json",
         "--transcripts", "transcripts", "--schema", "audit.schema.json"],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        print(f"FAIL: post-crash re-run does not pass verify_audit.py:\n{verify.stdout}{verify.stderr}")
        return 1

    print(f"PASS: after a mid-run SIGKILL, re-running produces a complete, verify-passing "
          f"audit.json with {len(keys)} records and no duplicates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
