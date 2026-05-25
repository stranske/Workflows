#!/usr/bin/env python3
"""Compare Gate detect-job outputs and flag invalid step-output references."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

STEP_OUTPUT_REF_RE = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return data


def _detect_job(workflow: dict[str, Any]) -> dict[str, Any]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError("workflow missing jobs mapping")
    detect = jobs.get("detect")
    if not isinstance(detect, dict):
        raise ValueError("workflow missing jobs.detect")
    return detect


def _step_ids(detect_job: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    steps = detect_job.get("steps", [])
    if not isinstance(steps, list):
        return ids
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        if isinstance(step_id, str) and step_id.strip():
            ids.add(step_id.strip())
    return ids


def _detect_outputs(detect_job: dict[str, Any]) -> dict[str, str]:
    outputs = detect_job.get("outputs", {})
    if not isinstance(outputs, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in outputs.items():
        if isinstance(key, str):
            normalized[key] = str(value)
    return normalized


def _output_refs(expr: str) -> list[tuple[str, str]]:
    return STEP_OUTPUT_REF_RE.findall(expr)


def compare_gate_detect_outputs(candidate_path: Path, baseline_path: Path) -> dict[str, Any]:
    candidate = _detect_job(_load_yaml(candidate_path))
    baseline = _detect_job(_load_yaml(baseline_path))

    candidate_outputs = _detect_outputs(candidate)
    baseline_outputs = _detect_outputs(baseline)

    candidate_keys = set(candidate_outputs.keys())
    baseline_keys = set(baseline_outputs.keys())
    candidate_step_ids = _step_ids(candidate)

    invalid_refs: dict[str, list[str]] = {}
    for output_name, expr in candidate_outputs.items():
        missing = sorted(
            {step_id for step_id, _ in _output_refs(expr) if step_id not in candidate_step_ids}
        )
        if missing:
            invalid_refs[output_name] = missing

    return {
        "candidate_path": str(candidate_path),
        "baseline_path": str(baseline_path),
        "candidate_output_count": len(candidate_keys),
        "baseline_output_count": len(baseline_keys),
        "added_outputs_vs_baseline": sorted(candidate_keys - baseline_keys),
        "removed_outputs_vs_baseline": sorted(baseline_keys - candidate_keys),
        "candidate_step_ids": sorted(candidate_step_ids),
        "invalid_step_output_references": invalid_refs,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate", required=True, type=Path, help="Candidate Gate workflow path"
    )
    parser.add_argument(
        "--baseline", required=True, type=Path, help="Known-green Gate workflow path"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = compare_gate_detect_outputs(args.candidate, args.baseline)
    print(json.dumps(report, indent=2))
    return 1 if report["invalid_step_output_references"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
