"""Check supplied hosted subscription evidence for consistency, without inference.

This offline check does not authenticate downloaded files or prove delivery. The
operator must verify the delivered SHA and that all inputs belong to one hosted
round. Pass the registry from that SHA and the JSON received by summary consumers,
not reconstructed expected outputs. Never supply authentication files.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

TIMESTAMP = re.compile(r"^\ufeff?\d{4}-\d\d-\d\dT\S+Z ")
SUPPRESSED_OUTPUT = re.compile(
    r"^(?:##\[warning\])?Skip output 'llm-"
    r"(?:analysis-run|provider|model|confidence|completed-tasks)' since it may contain secret\.$"
)
WORKFLOW = "stranske/Workflows/.github/workflows/reusable-codex-run.yml"
RECEIPTS = {
    "subscription-auth": "chatgpt",
    "OPENAI_API_KEY-present": "false",
    "ANTHROPIC_API_KEY-present": "false",
}


def _runtime_lines(log: str) -> list[str]:
    """Exclude Actions' echoed script and environment groups from receipts."""
    lines = []
    grouped = False
    for raw in log.splitlines():
        line = TIMESTAMP.sub("", raw)
        if line.startswith("##[group]"):
            grouped = True
        elif line == "##[endgroup]":
            grouped = False
        elif not grouped:
            lines.append(line)
    if grouped:
        raise ValueError("Analysis log ends inside an Actions group")
    return lines


def validate_evidence(*, delivered_sha, runner_log, analysis_log, analysis, summary, registry):
    """Raise on incomplete, contradictory or mismatched supplied evidence."""
    if not re.fullmatch(r"[0-9a-f]{40}", delivered_sha):
        raise ValueError("A full delivered commit SHA is required")
    uses = re.compile(rf"Uses: {re.escape(WORKFLOW)}@\S+ \(([0-9a-f]{{40}})\)")
    revisions = [
        match.group(1)
        for raw in runner_log.splitlines()
        if (match := uses.fullmatch(TIMESTAMP.sub("", raw)))
    ]
    if revisions != [delivered_sha]:
        raise ValueError("Runner workflow revision does not uniquely match delivered SHA")
    # Runner warnings can occur inside output groups. A matching downstream
    # fallback (especially []) cannot establish receipt of a suppressed output.
    if any(SUPPRESSED_OUTPUT.fullmatch(TIMESTAMP.sub("", raw)) for raw in runner_log.splitlines()):
        raise ValueError("Runner suppressed a required analysis output")

    profile = registry["subscription_analysis"]["codex"]
    model = (
        registry["execution_profiles"][profile["execution_profile"]]["model"]
        if "execution_profile" in profile
        else profile["model"]
    )
    if not isinstance(model, str) or not model:
        raise ValueError("Registry analysis model is missing")
    if analysis.get("provider") != "codex" or analysis.get("model") != model:
        raise ValueError("Analysis provider or registry model does not match")
    confidence = analysis.get("confidence")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise ValueError("Analysis confidence must be a finite number between zero and one")
    tasks = analysis.get("completed_tasks")
    if not isinstance(tasks, list) or any(not isinstance(task, str) for task in tasks):
        raise ValueError("Analysis completed tasks must be a list of strings")

    lines = _runtime_lines(analysis_log)
    expected = {**RECEIPTS, "completed-tasks-count": str(len(tasks))}
    for name, value in expected.items():
        observed = [line for line in lines if line.startswith(name + "=")]
        if observed != [f"{name}={value}"]:
            raise ValueError(f"Missing or conflicting runtime receipt: {name}")

    expected_outputs = {
        "llm-analysis-run": "true",
        "llm-provider": "codex",
        "llm-model": model,
        "llm-confidence": str(confidence),
    }
    if any(summary.get(key) != value for key, value in expected_outputs.items()):
        raise ValueError("Summary outputs do not match the analysis JSON")
    try:
        received_tasks = json.loads(summary["llm-completed-tasks"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Summary completed tasks are missing or invalid") from None
    if received_tasks != tasks:
        raise ValueError("Summary completed tasks do not match the analysis JSON")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivered-sha", required=True)
    for name in ("runner-log", "analysis-log", "analysis-json", "summary-json", "registry"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate_evidence(
            delivered_sha=args.delivered_sha,
            runner_log=args.runner_log.read_text(encoding="utf-8"),
            analysis_log=args.analysis_log.read_text(encoding="utf-8"),
            analysis=json.loads(args.analysis_json.read_text(encoding="utf-8")),
            summary=json.loads(args.summary_json.read_text(encoding="utf-8")),
            registry=yaml.safe_load(args.registry.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError):
        # Do not echo untrusted JSON, task text, log lines, paths or values.
        print("Evidence consistency check failed: incomplete or mismatched inputs")
        return 1
    print("Evidence consistency check passed; independently verify hosted provenance and delivery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
