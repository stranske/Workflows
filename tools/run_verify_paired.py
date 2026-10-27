"""Fixed public two-case screen through the existing semantic compare CLI.

This command has no repository mutation client. Policy approval is source owned;
preparing a packet or supplying credentials cannot enable a proposed trial.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "config/verify_paired"
PROPOSAL_SHA256 = "3423da3d0c0f243f10d83f57e2243d5ce04b30511b5dbd589919b5ca4e3620b9"
CASES = ("square-pass", "square-nonpass")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_packet() -> tuple[dict, dict]:
    proposal_bytes = (PACKET / "PROPOSAL.json").read_bytes()
    if digest(proposal_bytes) != PROPOSAL_SHA256:
        raise ValueError("reviewed proposal digest mismatch")
    proposal = json.loads(proposal_bytes)
    for name, expected in proposal["frozen_files"].items():
        # The original preparer's build program is retained as provenance in
        # its original packet; this runner never copies or executes it.
        if name == "build.py":
            continue
        if digest((PACKET / name).read_bytes()) != expected:
            raise ValueError(f"reviewed packet digest mismatch: {name}")
    if digest((PACKET / "REVIEW.json").read_bytes()) != proposal["independent_review"]["sha256"]:
        raise ValueError("independent packet review digest mismatch")
    policy = json.loads((PACKET / "trial-policy.json").read_text())
    if (
        policy["schema"] != "verify-paired-trial-policy/v1"
        or policy["max_generations"] != 4
        or policy["max_native_counts"] != 8
        or policy["max_native_metadata_requests"] != 6
        or policy["retries"] != 0
        or policy["fallback"] is not False
        or policy["repair_calls"] != 0
        or policy["models"]
        != [
            {"provider": "openai", "model": "gpt-5.6-terra"},
            {"provider": "anthropic", "model": "claude-sonnet-5-5"},
        ]
    ):
        raise ValueError("unsupported paired trial policy")
    for field, ceiling in (
        ("per_request_timeout_seconds", 30),
        ("total_wall_seconds", 300),
        ("max_output_tokens", 4096),
    ):
        if type(policy[field]) is not int or not 0 < policy[field] <= ceiling:
            raise ValueError(f"invalid reviewed policy cap: {field}")
    return proposal, policy


def child_environment(case: str, directory: Path, key: Path) -> dict[str, str]:
    # No PR/GitHub token, subscription auth, custom endpoint or slot/model
    # override is inherited. Values are passed to existing clients, never logged.
    allowed = (
        "PATH",
        "HOME",
        "SYSTEMROOT",
        "TMPDIR",
        "VIRTUAL_ENV",
        "OPENAI_API_KEY",
        "CLAUDE_API_STRANSKE",
    )
    env = {name: os.environ[name] for name in allowed if name in os.environ}
    capture = json.loads((PACKET / case / "capture.json").read_text())
    env.update(
        PYTHONPATH=str(ROOT),
        VERIFIER_SEMANTIC_MODE="1",
        VERIFIER_SEMANTIC_KEY_PATH=str(key),
        VERIFIER_PAIRED_QUALIFICATION=case,
        PR_HEAD_SHA=capture["implementation_head"],
        VERIFIER_EVIDENCE_CAPTURE_DIR=str(directory),
        LANGCHAIN_SLOT_CONFIG=str(PACKET / "slots.json"),
        LANGCHAIN_MODEL_REGISTRY_CONFIG=str(ROOT / "config/model_registry.json"),
    )
    return env


def run(*, execute: bool) -> dict:
    proposal, policy = load_packet()
    output = Path(os.environ["RUNNER_TEMP"]) / "verify-paired"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {
        "schema": "verify-paired-invocation/v1",
        "status": "prepared",
        "proposal_sha256": PROPOSAL_SHA256,
        "packet_source_head": proposal["source_head"],
        "policy": policy,
        "cases": proposal["cases"],
        "native_capacity_claim": False,
        "role_qualification_claim": False,
        "semantic_cli_started": False,
        "native_request_state": "not_started",
        "results": [],
    }
    key = output / ".semantic-key"
    try:
        for name in (
            "PROPOSAL.json",
            "REVIEW.json",
            "build-receipt.json",
            "trial-policy.json",
            "slots.json",
        ):
            shutil.copyfile(PACKET / name, output / name)
        if not execute:
            return receipt
        if policy.get("execution_enabled") is not True or policy.get("review_status") != "reviewed":
            receipt.update(status="held", reason="trial policy awaits Core/executor review")
            return receipt
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        deadline = time.monotonic() + policy["total_wall_seconds"]
        for case in CASES:
            directory = output / case
            shutil.copytree(PACKET / case, directory)
            argv = [
                sys.executable,
                str(ROOT / "scripts/langchain/pr_verifier.py"),
                "--context-file",
                str(directory / "context.md"),
                "--diff-file",
                str(directory / "diff.patch"),
                "--compare",
                "--json",
                "--output-file",
                str(directory / "report.md"),
            ]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("paired trial wall policy exhausted")
            receipt["semantic_cli_started"] = True
            receipt["native_request_state"] = "unknown"
            with (
                (directory / "comparison.json").open("wb") as stdout,
                (directory / "diagnostic.log").open("wb") as stderr,
            ):
                completed = subprocess.run(
                    argv,
                    cwd=ROOT,
                    env=child_environment(case, directory, key),
                    stdout=stdout,
                    stderr=stderr,
                    timeout=remaining,
                    check=False,
                )
            receipt["results"].append({"case": case, "returncode": completed.returncode})
            if completed.returncode:
                raise ValueError("semantic CLI failed; no retry or replacement")
            report = json.loads((directory / "comparison.json").read_text())
            trial = report.get("semantic_acceptance", {}).get("qualification_trial", {})
            attempted = trial.get("attempted_native_requests")
            if (
                trial.get("case") == case
                and trial.get("policy") == policy
                and isinstance(attempted, dict)
                and set(attempted) == {"generation", "count", "metadata"}
                and all(type(value) is int and value >= 0 for value in attempted.values())
            ):
                receipt["results"][-1]["attempted_native_requests"] = attempted
                receipt["native_request_state"] = (
                    "attempts_recorded"
                    if any(
                        sum(row.get("attempted_native_requests", {}).values())
                        for row in receipt["results"]
                    )
                    else "not_started"
                )
            arms = report.get("results", [])
            if len(arms) != 2 or any(
                arm.get("used_llm") is not True or arm.get("error") for arm in arms
            ):
                raise ValueError("native pair incomplete; retain raw output and stop")
        receipt["status"] = "completed_screen_only"
        return receipt
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
        receipt.update(status="held", reason=str(exc))
        return receipt
    finally:
        key.unlink(missing_ok=True)
        (output / "invocation.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Requires reviewed source policy.")
    args = parser.parse_args()
    receipt = run(execute=args.execute)
    print(json.dumps(receipt, indent=2))
    if receipt["status"] == "held":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
