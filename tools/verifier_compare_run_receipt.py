"""Build dual-run verify:compare receipts that freeze a baseline NON_PASS.

Orphan Steward uses this after a repaired-input compare for release PR #3769.
The original production run (37400729553) stays CONCERNS/NON_PASS; attaching a
follow-up run records new verdicts and artifact inventory without relabeling
the baseline.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "workflows-verifier-compare-receipt/v1"
BASELINE_RUN_ID = "37400729553"
BASELINE_PR = "3769"

COMPARISON_ARTIFACT_FILES = (
    "comparison.json",
    "comparison-stderr.log",
    "comparison-comment.md",
    "verifier-context.md",
    "verifier-diff-summary.md",
    "verifier-pr-diff.patch",
    "verifier-input-manifest.json",
)

COMPARISON_ARTIFACT_NAME = "comparison-results-{run_id}"
TERMINAL_ARTIFACT_NAME = "verifier-terminal-disposition-{run_id}"
METRICS_ARTIFACT_NAME = "agents-verifier-metrics"

_DISCOVERY_RE = re.compile(
    r'"acceptance_source_discovery"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})',
    re.MULTILINE,
)
_CORPUS_DECISION_RE = re.compile(
    r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->",
)


def inventory_from_comparison_dir(comparison_dir: Path) -> dict[str, Any]:
    """List the seven comparison-bundle files and whether each exists."""
    present = sorted(path.name for path in comparison_dir.iterdir() if path.is_file())
    missing = [name for name in COMPARISON_ARTIFACT_FILES if name not in present]
    return {
        "artifact_name": None,
        "expected_files": list(COMPARISON_ARTIFACT_FILES),
        "present_files": present,
        "missing_files": missing,
        "complete": not missing,
        "file_count": len(present),
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_discovery(context_text: str) -> dict[str, Any] | None:
    match = _DISCOVERY_RE.search(context_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_corpus_decision(comment_text: str) -> dict[str, Any] | None:
    match = _CORPUS_DECISION_RE.search(comment_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _provider_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        rows.append(
            {
                "model": result.get("model"),
                "verdict": str(result.get("verdict", "")).upper() or None,
                "confidence": result.get("confidence"),
                "used_llm": bool(result.get("used_llm")),
            }
        )
    return rows


def summarize_compare_run(
    *,
    run_id: str,
    comparison_dir: Path,
    terminal_disposition: dict[str, Any] | None = None,
    role: str = "baseline",
) -> dict[str, Any]:
    """Summarize one compare run from a downloaded comparison-results directory."""
    if not re.fullmatch(r"\d+", str(run_id)) or int(run_id) < 1:
        raise ValueError(f"run_id must be a positive integer string, got {run_id!r}")
    if role not in {"baseline", "followup"}:
        raise ValueError(f"role must be baseline or followup, got {role!r}")
    if not comparison_dir.is_dir():
        raise FileNotFoundError(f"comparison directory not found: {comparison_dir}")

    inventory = inventory_from_comparison_dir(comparison_dir)
    inventory["artifact_name"] = COMPARISON_ARTIFACT_NAME.format(run_id=run_id)

    comparison = _load_json(comparison_dir / "comparison.json")
    results = comparison.get("results", []) if isinstance(comparison, dict) else []
    if not isinstance(results, list):
        results = []

    comment_path = comparison_dir / "comparison-comment.md"
    context_path = comparison_dir / "verifier-context.md"
    manifest_path = comparison_dir / "verifier-input-manifest.json"

    comment_text = comment_path.read_text(encoding="utf-8") if comment_path.is_file() else ""
    context_text = context_path.read_text(encoding="utf-8") if context_path.is_file() else ""
    manifest = _load_json(manifest_path) if manifest_path.is_file() else {}

    corpus_decision = _parse_corpus_decision(comment_text)
    discovery = _parse_discovery(context_text)
    identity_sources = [
        ("manifest", manifest.get("source_run_id"), manifest.get("repository"), manifest.get("pr")),
        (
            "corpus",
            (corpus_decision or {}).get("run_id"),
            (corpus_decision or {}).get("repo"),
            (corpus_decision or {}).get("pr"),
        ),
        (
            "terminal",
            (terminal_disposition or {}).get("run_id"),
            (terminal_disposition or {}).get("repository"),
            (terminal_disposition or {}).get("pr_number"),
        ),
    ]
    if not any(run for _, run, _, _ in identity_sources):
        raise ValueError("run identity is unavailable in comparison artifacts")
    for source, recorded_run, _, _ in identity_sources:
        if recorded_run is not None and str(recorded_run) != str(run_id):
            raise ValueError(f"run identity mismatch in {source}: {recorded_run!r} != {run_id!r}")
    for index, label in [(2, "repository"), (3, "pr")]:
        identities = {str(row[index]) for row in identity_sources if row[index] is not None}
        if len(identities) > 1:
            raise ValueError(f"target identity mismatch for {label}: {sorted(identities)}")
    provider_verdicts = [row["verdict"] for row in _provider_rows(results) if row.get("verdict")]

    summary: dict[str, Any] = {
        "role": role,
        "run_id": str(run_id),
        "pr": str(manifest.get("pr") or (corpus_decision or {}).get("pr") or ""),
        "repository": str(manifest.get("repository") or (corpus_decision or {}).get("repo") or ""),
        "head_sha": (corpus_decision or {}).get("head_sha") or manifest.get("head_sha"),
        "merge_sha": manifest.get("merge_sha") or (corpus_decision or {}).get("evaluated_sha"),
        "provider_verdicts": provider_verdicts,
        "provider_rows": _provider_rows(results),
        "corpus_verdict": (corpus_decision or {}).get("verdict"),
        "corpus_decision": corpus_decision,
        "acceptance_source_discovery": discovery,
        "artifact_inventory": {
            "comparison_results": inventory,
            "terminal_disposition": {
                "artifact_name": TERMINAL_ARTIFACT_NAME.format(run_id=run_id),
                "present": terminal_disposition is not None,
                "disposition": (terminal_disposition or {}).get("disposition"),
                "verdict": (terminal_disposition or {}).get("verdict"),
            },
            "metrics": {"artifact_name": METRICS_ARTIFACT_NAME},
        },
        "immutable": role == "baseline",
    }
    return summary


def _followup_comparison_complete(followup: dict[str, Any]) -> bool:
    inventory = (followup.get("artifact_inventory") or {}).get("comparison_results") or {}
    return bool(inventory.get("complete")) and not inventory.get("missing_files")


def _followup_repairs_release_source(followup: dict[str, Any]) -> bool:
    """True when follow-up discovery no longer requires incidental #3768."""
    discovery = followup.get("acceptance_source_discovery") or {}
    if not isinstance(discovery, dict):
        return False
    if discovery.get("required") is True:
        return False
    reason = str(discovery.get("reason") or "")
    # Baseline misclassification text must not reappear as a required contract.
    if "#3768" in reason and "not retrieved" in reason.lower():
        return False
    return True


def build_dual_run_receipt(
    *,
    baseline: dict[str, Any],
    followup: dict[str, Any] | None = None,
    expected_baseline_run_id: str = BASELINE_RUN_ID,
    require_followup_repair: bool = True,
) -> dict[str, Any]:
    """Combine baseline + optional follow-up without mutating baseline fields."""
    if baseline.get("run_id") != expected_baseline_run_id:
        raise ValueError(
            f"baseline run_id must remain {expected_baseline_run_id}, "
            f"got {baseline.get('run_id')!r}"
        )
    if baseline.get("role") != "baseline":
        raise ValueError("baseline.role must be 'baseline'")
    if baseline.get("corpus_verdict") != "NON_PASS":
        raise ValueError(
            "baseline corpus_verdict must remain NON_PASS; "
            f"got {baseline.get('corpus_verdict')!r}"
        )
    if baseline.get("provider_verdicts") != ["CONCERNS", "CONCERNS"]:
        raise ValueError(
            "baseline provider_verdicts must remain CONCERNS/CONCERNS; "
            f"got {baseline.get('provider_verdicts')!r}"
        )

    if baseline.get("repository") != "stranske/Workflows" or str(baseline.get("pr")) != BASELINE_PR:
        raise ValueError("baseline target identity must be stranske/Workflows#3769")

    frozen_baseline = json.loads(json.dumps(baseline))
    frozen_baseline["role"] = "baseline"
    frozen_baseline["immutable"] = True

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "pr": BASELINE_PR,
        "repository": frozen_baseline.get("repository") or "stranske/Workflows",
        "baseline": frozen_baseline,
        "followup": None,
        "baseline_preserved": True,
        "independent_gates": {
            "source_3757_topology": "required_external",
            "complete_artifact_count_evidence": "required_on_followup_comparison_bundle",
        },
        "steward_dispatch": {
            "workflow": "agents-verifier.yml",
            "mode": "compare",
            "pr_number": BASELINE_PR,
            "command": (
                "gh workflow run agents-verifier.yml "
                "--repo stranske/Workflows "
                "-f pr_number=3769 -f mode=compare"
            ),
        },
    }

    if followup is None:
        return receipt

    if followup.get("role") != "followup":
        raise ValueError("followup.role must be 'followup'")
    if followup.get("run_id") == expected_baseline_run_id:
        raise ValueError(
            "followup run_id must differ from the frozen baseline " f"{expected_baseline_run_id}"
        )
    if not re.fullmatch(r"[1-9]\d*", str(followup.get("run_id", ""))):
        raise ValueError("followup.run_id must be a positive integer string")

    if any(str(followup.get(key)) != str(baseline.get(key)) for key in ("repository", "pr")):
        raise ValueError("followup target identity must match the frozen baseline")

    if not _followup_comparison_complete(followup):
        raise ValueError("followup comparison artifact inventory must be complete")

    if require_followup_repair and not _followup_repairs_release_source(followup):
        raise ValueError(
            "followup must demonstrate repaired source discovery "
            "(#3768 must not remain a required unavailable source issue)"
        )

    attached = json.loads(json.dumps(followup))
    attached["role"] = "followup"
    attached["immutable"] = False
    attached["source_repair_demonstrated"] = _followup_repairs_release_source(followup)
    receipt["followup"] = attached

    # Re-check baseline identity after attach — never allow silent relabel.
    if receipt["baseline"] != frozen_baseline:
        raise RuntimeError("baseline fields changed while attaching followup")
    if receipt["baseline"]["run_id"] != expected_baseline_run_id:
        raise RuntimeError("baseline run_id was relabeled")
    if receipt["baseline"]["corpus_verdict"] != "NON_PASS":
        raise RuntimeError("baseline corpus_verdict was relabeled")
    receipt["baseline_preserved"] = True
    return receipt


def load_terminal_disposition(path: Path) -> dict[str, Any]:
    """Load the first NDJSON terminal-disposition record from a file or directory."""
    if path.is_dir():
        candidates = sorted(path.rglob("verifier-terminal-disposition.ndjson"))
        if not candidates:
            raise FileNotFoundError(f"verifier-terminal-disposition.ndjson not found under {path}")
        path = candidates[0]
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"no terminal disposition records in {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-id", default=BASELINE_RUN_ID)
    parser.add_argument("--baseline-comparison-dir", type=Path, required=True)
    parser.add_argument("--baseline-terminal", type=Path)
    parser.add_argument("--followup-run-id")
    parser.add_argument("--followup-comparison-dir", type=Path)
    parser.add_argument("--followup-terminal", type=Path)
    parser.add_argument("--output", type=Path, help="Write receipt JSON to this path")
    args = parser.parse_args(argv)

    baseline_terminal = (
        load_terminal_disposition(args.baseline_terminal) if args.baseline_terminal else None
    )
    baseline = summarize_compare_run(
        run_id=args.baseline_run_id,
        comparison_dir=args.baseline_comparison_dir,
        terminal_disposition=baseline_terminal,
        role="baseline",
    )

    followup = None
    if args.followup_run_id or args.followup_comparison_dir:
        if not args.followup_run_id or not args.followup_comparison_dir:
            parser.error("followup requires both --followup-run-id and --followup-comparison-dir")
        followup_terminal = (
            load_terminal_disposition(args.followup_terminal) if args.followup_terminal else None
        )
        followup = summarize_compare_run(
            run_id=args.followup_run_id,
            comparison_dir=args.followup_comparison_dir,
            terminal_disposition=followup_terminal,
            role="followup",
        )

    receipt = build_dual_run_receipt(
        baseline=baseline,
        followup=followup,
        expected_baseline_run_id=args.baseline_run_id,
    )
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
