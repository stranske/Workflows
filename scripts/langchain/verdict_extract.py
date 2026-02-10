"""Entrypoint for deterministic verdict extraction with structured outputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TypedDict

from scripts.langchain import verdict_policy


def build_verdict_result(
    summary: str,
    *,
    policy: str = "worst",
) -> verdict_policy.VerdictPolicyResult:
    return verdict_policy.evaluate_summary(summary, policy=policy)


class VerdictGithubOutputs(TypedDict):
    verdict: str
    needs_human: str
    needs_human_reason: str
    policy: str
    verdict_kind: str
    selected_provider: str
    selected_model: str
    selected_confidence: str
    split_verdict: str
    concerns_confidence: str
    verdict_metadata: str


def _build_github_outputs(result: verdict_policy.VerdictPolicyResult) -> VerdictGithubOutputs:
    return {
        "verdict": result.verdict,
        "needs_human": str(result.needs_human).lower(),
        "needs_human_reason": result.needs_human_reason,
        "policy": result.policy,
        "verdict_kind": result.verdict_kind,
        "selected_provider": result.selected_provider or "",
        "selected_model": result.selected_model or "",
        "selected_confidence": (
            f"{result.selected_confidence:.4f}" if result.selected_confidence is not None else ""
        ),
        "split_verdict": str(result.split_verdict).lower(),
        "concerns_confidence": (
            f"{result.concerns_confidence:.4f}" if result.concerns_confidence is not None else ""
        ),
        "verdict_metadata": json.dumps(result.as_dict()),
    }


def _write_github_outputs(result: verdict_policy.VerdictPolicyResult, output_path: str) -> None:
    outputs = _build_github_outputs(result)

    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a deterministic verdict and emit structured outputs."
    )
    parser.add_argument(
        "--summary-path",
        required=True,
        help="Path to the markdown summary (use '-' for stdin).",
    )
    parser.add_argument(
        "--policy",
        choices=["worst", "majority"],
        default="worst",
        help="Policy used to resolve split provider verdicts.",
    )
    parser.add_argument(
        "--emit",
        choices=["github", "json", "verdict"],
        default="github",
        help="Output format for results.",
    )
    args = parser.parse_args(argv)

    summary = verdict_policy._read_summary(args.summary_path)
    result = build_verdict_result(summary, policy=args.policy)

    if args.emit == "verdict":
        print(result.verdict)
        return 0

    if args.emit == "json":
        print(json.dumps(result.as_dict(), indent=2))
        return 0

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if not github_output:
        print(
            "GITHUB_OUTPUT is not set; falling back to JSON on stdout.",
            file=sys.stderr,
        )
        print(json.dumps(result.as_dict(), indent=2))
        return 0

    _write_github_outputs(result, github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
