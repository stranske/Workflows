"""Deterministic signature self-test.

This script emulates the core hashing logic used in
the Gate summary job's failure-tracker path to provide a guardrail
that local changes to signature composition are intentional.

Usage:
    python tools/test_failure_signature.py \
        --jobs '[{"name":"Tests","step":"pytest","stack":"ValueError: boom"}]'

The script prints the derived 12-char hash and exits 0. Provide
`--expected <hash>` to assert a known value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys


def build_signature_hash(jobs: list[dict]) -> str:
    parts: list[str] = []
    for j in jobs:
        name = j.get("name", "?")
        step = j.get("step", "no-step")
        stack = j.get("stack", "no-stack")
        parts.append(f"{name}::{step}::{stack}")
    parts.sort()
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
    return h


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="JSON array of job dicts: name, step, stack")
    ap.add_argument("--expected", help="Assert the resulting hash equals this value")
    args = ap.parse_args(argv)
    try:
        jobs = json.loads(args.jobs)
        if not isinstance(jobs, list):  # pragma: no cover - defensive
            raise ValueError("--jobs must decode to a list")
    except Exception as e:  # pragma: no cover - parsing errors
        print(f"Invalid --jobs JSON: {e}", file=sys.stderr)
        return 2

    sig = build_signature_hash(jobs)
    print(sig)
    if args.expected and sig != args.expected:
        print(f"Hash mismatch: expected {args.expected} got {sig}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
