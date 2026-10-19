#!/usr/bin/env python3
"""Reproduce historical screen aggregates offline from versioned result rows.

This preserves digests and observations, never prompt text or new model calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from tools.analyze_judge_ensemble import analyze, load_judgments

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("docs/evidence/judge-screen-20261017")
SOURCE = DIRECTORY / "muse-spark-1-3-screen.json"
ARTIFACT = DIRECTORY / "standard-muse13-observations.json"
ENSEMBLE = DIRECTORY / "current-prompt-ensemble.json"
SOURCE_REVISION = "e888a4b159a8076882c94c5f309b73aee86a13cd"
SOURCE_SHA256 = "a8c23ecf2cedba58a367435dd16a0f5ae493f17b598f7864fb66977dc8f6af91"
INPUTS = [
    DIRECTORY / "current-prompt-codex-screen.json",
    DIRECTORY / "current-prompt-claude-cursor-muse12.json",
    ARTIFACT,
    DIRECTORY / "muse-spark-1-3-contributor-screen.json",
    DIRECTORY / "muse-spark-1-2-contributor-screen.json",
    DIRECTORY / "muse-wonder-1-0-screen.json",
]
COMMAND = "python -m tools.reproduce_muse13_screen --check"


def standard_observations(root: Path = ROOT) -> dict:
    raw = (root / SOURCE).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Pinned standard Muse 1.3 source digest changed")
    source = json.loads(raw)
    rows = []
    seen = set()
    for row in source["rows"]:
        case = row["case_id"]
        if case in seen or row["judge"] != "muse-api" or row["served_model"] != "muse-spark-1.3":
            raise ValueError("Unexpected or duplicate standard Muse observation")
        seen.add(case)
        digest = source["prompt_sha256_by_case"][case]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid recorded input digest")
        preserved = {
            k: row[k]
            for k in (
                "case_id",
                "category",
                "expected_verdict",
                "actual_verdict",
                "raw_verdict",
                "schema_valid",
                "served_model",
                "evidence_class",
                "tool_activity",
            )
        }
        preserved["prediction"] = row["raw_verdict"]
        preserved.update(
            judge="muse-api:muse-spark-1.3", input_digest=digest, source_revision=SOURCE_REVISION
        )
        rows.append(preserved)
    if seen != set(source["case_ids"]) or len(rows) != 8:
        raise ValueError("Expected the eight historical standard Muse cases")
    return {
        "schema": "workflows-judge-screen-preserved-observations/v1",
        "source_path": str(SOURCE),
        "source_revision": SOURCE_REVISION,
        "source_sha256": SOURCE_SHA256,
        "input_fingerprint": source["input_fingerprint"],
        "prompt_sha256_by_case": source["prompt_sha256_by_case"],
        "case_ids": source["case_ids"],
        "rows": rows,
        "limitations": [
            "Exact prompt text is absent from this artifact. Its public provenance and original text recovery are not established.",
            "Input digests are preserved historical records, not independently regenerated hashes of unavailable original prompt text.",
            "Predictions are versioned historical observations, not new model requests or proof of current provider quality.",
        ],
    }


def reproduced_ensemble(artifact: dict, root: Path = ROOT) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory) / ARTIFACT.name
        temporary.write_text(json.dumps(artifact))
        paths = [temporary if path == ARTIFACT else root / path for path in INPUTS]
        decisions, truth = load_judgments(paths)
        categories = {}
        for path in paths:
            for row in json.loads(path.read_text())["rows"]:
                case, category = row["case_id"], row["category"]
                if categories.setdefault(case, category) != category:
                    raise ValueError("Inconsistent category")
        return analyze(decisions, truth, bound=0.05, categories=categories)


def verify(*, write: bool = False, root: Path = ROOT) -> dict:
    artifact = standard_observations(root)
    actual = reproduced_ensemble(artifact, root)
    stored = json.loads((root / ENSEMBLE).read_text())
    # Compare the entire historical result, including all 36 pairs and 252 tie
    # breaks. The manifest/receipt adds provenance but changes no calculations.
    historical = {
        k: v
        for k, v in stored.items()
        if k not in {"ordered_input_manifest", "evidence_reproduction"}
    }
    if actual != historical:
        changed = sorted(
            k for k in actual.keys() | historical.keys() if actual.get(k) != historical.get(k)
        )
        raise ValueError(f"Stored ensemble differs from versioned observations: {changed}")
    receipt = {
        "artifact": str(ARTIFACT),
        "command": COMMAND,
        "source_revision": SOURCE_REVISION,
        "offline": True,
        "checked_sections": sorted(actual),
        "original_prompt_text_recovered": False,
    }
    manifest = [str(p) for p in INPUTS]
    if write:
        (root / ARTIFACT).write_text(json.dumps(artifact, indent=2) + "\n")
        stored.update(ordered_input_manifest=manifest, evidence_reproduction=receipt)
        (root / ENSEMBLE).write_text(json.dumps(stored, indent=2) + "\n")
    else:
        if json.loads((root / ARTIFACT).read_text()) != artifact:
            raise ValueError("Preserved standard Muse case artifact differs")
        if (
            stored.get("ordered_input_manifest") != manifest
            or stored.get("evidence_reproduction") != receipt
        ):
            raise ValueError("Missing or changed versioned reproduction receipt")
    return {
        "cases": actual["cases"],
        "judges": len(actual["judges"]),
        "pairs": len(actual["pairs"]),
        "tie_breaks": len(actual["tie_breaks"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(write=args.write), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
