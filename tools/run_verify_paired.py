"""Fixed public two-case screen through the existing semantic compare CLI.

This command has no repository mutation client. Policy approval is source owned;
preparing a packet or supplying credentials cannot enable a proposed trial.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "config/verify_paired"
DESCRIPTOR_PATH = PACKET / "descriptor.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_path(base: Path, name: str, *, allow_root: bool = False) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("invalid source-owned packet path")
    parts = name.split("/")
    if name == "." and allow_root:
        parts = []
    elif any(part in {"", ".", ".."} for part in parts) or Path(name).is_absolute():
        raise ValueError("source-owned packet path must stay within its namespace")
    target = base
    ancestors = [base]
    if base.is_relative_to(ROOT):
        ancestors.extend(parent for parent in base.parents if parent.is_relative_to(ROOT))
    if any(path.is_symlink() for path in ancestors):
        raise ValueError("source-owned packet namespace cannot be a symlink")
    for part in parts:
        target /= part
        if target.is_symlink():
            raise ValueError("source-owned packet paths cannot be symlinks")
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError("source-owned packet escaped its namespace")
    return target


def _source_json(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate source descriptor member")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("source descriptor must be an object")
    return value


def _source_bytes(base: Path, name: str) -> bytes:
    path = _source_path(base, name)
    if not path.is_file():
        raise ValueError("source packet member must be a regular file")
    return path.read_bytes()


def source_descriptor() -> dict:
    relative = DESCRIPTOR_PATH.relative_to(PACKET).as_posix()
    raw = _source_bytes(PACKET, relative)
    descriptor = _source_json(raw)
    if (
        set(descriptor)
        != {
            "schema",
            "packet_root",
            "proposal_sha256",
            "review_sha256",
            "policy_file",
            "policy_sha256",
            "slots_file",
            "slots_sha256",
            "cases",
        }
        or descriptor.get("schema") != "verify-paired-source-descriptor/v1"
    ):
        raise ValueError("unknown source-owned packet descriptor")
    cases = descriptor["cases"]
    if (
        not isinstance(cases, list)
        or not 1 <= len(cases) <= 2
        or any(
            type(case) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", case)
            for case in cases
        )
        or len(set(cases)) != len(cases)
    ):
        raise ValueError("source descriptor requires one or two distinct fixed cases")
    for field in ("proposal_sha256", "review_sha256", "policy_sha256", "slots_sha256"):
        if type(descriptor[field]) is not str or not re.fullmatch(
            r"[a-f0-9]{64}", descriptor[field]
        ):
            raise ValueError("source descriptor digest malformed")
    return {
        **descriptor,
        "sha256": digest(raw),
        "root": _source_path(PACKET, descriptor["packet_root"], allow_root=True),
        "policy_path": _source_path(PACKET, descriptor["policy_file"]),
        "slots_path": _source_path(PACKET, descriptor["slots_file"]),
    }


def runtime_dependencies() -> dict:
    """Local package observations; the native job must separately attest origin."""
    lock = (ROOT / "requirements.lock").read_text()
    installed = {}
    expected = {}
    for name in (
        "openai",
        "anthropic",
        "langchain-openai",
        "langchain-anthropic",
        "httpx",
        "pydantic",
        "langchain-core",
    ):
        pins = re.findall(rf"^{re.escape(name)}==([^\s;]+)$", lock, flags=re.MULTILINE)
        if len(pins) != 1:
            raise ValueError("paired runtime dependency lacks one exact existing lock pin")
        expected[name] = pins[0]
        try:
            installed[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed[name] = None
    return {"installed": installed, "locked": expected, "matches_lock": installed == expected}


def load_packet() -> tuple[dict, dict]:
    descriptor = source_descriptor()
    packet = descriptor["root"]
    proposal_bytes = _source_bytes(packet, "PROPOSAL.json")
    if digest(proposal_bytes) != descriptor["proposal_sha256"]:
        raise ValueError("reviewed proposal digest mismatch")
    proposal = _source_json(proposal_bytes)
    if proposal.get("schema") not in {
        "verify-public-api-paired-proposal/v1",
        "verify-paired-packet/v1",
    }:
        raise ValueError("unsupported fixed packet schema")
    if (
        not isinstance(proposal.get("cases"), list)
        or any(not isinstance(row, dict) for row in proposal["cases"])
        or not isinstance(proposal.get("frozen_files"), dict)
        or not isinstance(proposal.get("independent_review"), dict)
    ):
        raise ValueError("fixed packet inventory or cases malformed")
    if [row.get("case") for row in proposal["cases"]] != descriptor["cases"]:
        raise ValueError("packet cases differ from reviewed source descriptor")
    for name, expected in proposal["frozen_files"].items():
        # The original preparer's build program is retained as provenance in
        # its original packet; this runner never copies or executes it.
        if name == "build.py" and proposal["schema"] == "verify-public-api-paired-proposal/v1":
            continue
        if (
            type(expected) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", expected)
            or digest(_source_bytes(packet, name)) != expected
        ):
            raise ValueError(f"reviewed packet digest mismatch: {name}")
    for case in descriptor["cases"]:
        directory = _source_path(packet, case)
        actual = set()
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("reviewed case inventory cannot contain symlinks")
            if path.is_file():
                actual.add(path.relative_to(packet).as_posix())
            elif not path.is_dir():
                raise ValueError("reviewed case inventory contains a non-regular member")
        expected = {name for name in proposal["frozen_files"] if name.startswith(case + "/")}
        mandatory = {
            case + "/" + name
            for name in ("capture.json", "context.md", "diff.patch", "prompt.txt", "oracle.json")
        }
        if actual != expected or not mandatory <= actual:
            raise ValueError("reviewed case inventory is incomplete or has unexpected members")
        row = next(row for row in proposal["cases"] if row["case"] == case)
        if (
            any(
                type(row.get(field)) is not str or not re.fullmatch(r"[a-f0-9]{64}", row[field])
                for field in ("prompt_sha256", "capture_id", "gold_sha256")
            )
            or digest((directory / "prompt.txt").read_bytes()) != row["prompt_sha256"]
            or digest((directory / "oracle.json").read_bytes()) != row["gold_sha256"]
            or _source_json((directory / "capture.json").read_bytes()).get("id")
            != row["capture_id"]
        ):
            raise ValueError("fixed case capture, prompt or gold identity differs from proposal")
    if (
        (
            proposal["schema"] == "verify-paired-packet/v1"
            and proposal["independent_review"].get("path") != "REVIEW.json"
        )
        or digest(_source_bytes(packet, "REVIEW.json")) != descriptor["review_sha256"]
        or descriptor["review_sha256"] != proposal["independent_review"].get("sha256")
    ):
        raise ValueError("independent packet review digest mismatch")
    policy_bytes = _source_bytes(PACKET, descriptor["policy_file"])
    if (
        digest(policy_bytes) != descriptor["policy_sha256"]
        or digest(_source_bytes(PACKET, descriptor["slots_file"])) != descriptor["slots_sha256"]
    ):
        raise ValueError("source-owned policy or slots digest mismatch")
    policy = _source_json(policy_bytes)
    required = {
        "schema",
        "review_status",
        "execution_enabled",
        "max_generations",
        "max_native_counts",
        "per_request_timeout_seconds",
        "total_wall_seconds",
        "max_output_tokens",
        "retries",
        "fallback",
        "repair_calls",
        "models",
        "native_capacity_claim",
        "role_qualification_claim",
        "max_native_metadata_requests",
        "max_physical_http_attempts",
        "max_redirects",
    }
    if (
        set(policy) not in (required, required | {"preserve_native_output_policy"})
        or type(policy.get("execution_enabled")) is not bool
        or policy.get("review_status") not in {"proposed_source_only", "reviewed"}
        or policy.get("native_capacity_claim") is not False
        or policy.get("role_qualification_claim") is not False
    ):
        raise ValueError("unknown or malformed source-owned trial policy")
    if any(
        type(policy[field]) is not int or policy[field] != value
        for field, value in {
            "max_generations": 4,
            "max_native_counts": 8,
            "max_native_metadata_requests": 6,
            "retries": 0,
            "repair_calls": 0,
        }.items()
    ):
        raise ValueError("logical trial budget differs from reviewed finite limits")
    if (
        policy["schema"] != "verify-paired-trial-policy/v1"
        or policy["max_generations"] != 4
        or policy["max_native_counts"] != 8
        or policy["max_native_metadata_requests"] != 6
        or type(policy.get("max_physical_http_attempts")) is not int
        or policy["max_physical_http_attempts"] != 18
        or type(policy.get("max_redirects")) is not int
        or policy["max_redirects"] != 0
        or policy["retries"] != 0
        or policy["fallback"] is not False
        or policy["repair_calls"] != 0
        or policy["models"]
        not in (
            [
                {"provider": "openai", "model": "gpt-5.6-terra"},
                {"provider": "anthropic", "model": "claude-sonnet-5-5"},
            ],
            [
                {"provider": "openai", "model": "gpt-5.6-terra"},
                {"provider": "anthropic", "model": "claude-opus-5-5"},
            ],
        )
    ):
        raise ValueError("unsupported paired trial policy")
    for field, ceiling in (
        ("per_request_timeout_seconds", 60),
        ("total_wall_seconds", 600),
        ("max_output_tokens", 128000),
    ):
        if type(policy[field]) is not int or not 0 < policy[field] <= ceiling:
            raise ValueError(f"invalid reviewed policy cap: {field}")
    if type(policy.get("preserve_native_output_policy", False)) is not bool:
        raise ValueError("invalid native output policy")
    if policy.get("preserve_native_output_policy") is True and (
        policy["max_output_tokens"] != 128000
        or policy["models"][1]["model"] != "claude-opus-5-5"
        or policy["per_request_timeout_seconds"] != 60
        or policy["total_wall_seconds"] != 600
    ):
        raise ValueError(
            "representative packet must preserve exact production native output policy"
        )
    return proposal, policy


@contextmanager
def _capture_environment(directory: Path, head: str):
    updates = {
        "PR_HEAD_SHA": head,
        "VERIFIER_EVIDENCE_CAPTURE_DIR": str(directory),
        "CHAIN_DEPTH": "0",
    }
    previous = {name: os.environ.get(name) for name in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def preflight_inputs(descriptor: dict, proposal: dict) -> dict:
    """Check every fixed input before constructing any provider client."""
    from scripts.langchain import pr_verifier as verifier

    receipts = {}
    for case in descriptor["cases"]:
        directory = descriptor["root"] / case
        original = _source_json((directory / "capture.json").read_bytes())
        row = next(row for row in proposal["cases"] if row["case"] == case)
        with _capture_environment(directory, original["implementation_head"]):
            context = (directory / "context.md").read_text()
            diff = (directory / "diff.patch").read_text()
            capture = verifier._semantic_capture(context, diff)
            if capture != original or capture["gaps"] or not capture["resource_admitted"]:
                raise ValueError("fixed packet capture is incomplete or changed")
            raw = verifier._semantic_raw_inputs(context, diff)
            prepared = verifier.prepare_reviewed_execution(capture, raw)
            if prepared is None:
                prepared = verifier.prepare_residual_all_input(capture, raw)
            packages = prepared["plan"]["packages"]
            if len(packages) != 1:
                raise ValueError("fixed packet must have one complete semantic package")
            prompt = verifier._semantic_package_prompt(prepared, packages[0], prepared["contract"])
            if (
                digest(prompt.encode()) != row["prompt_sha256"]
                or prompt.encode() != (directory / "prompt.txt").read_bytes()
            ):
                raise ValueError(
                    "current complete native prompt differs from frozen production prompt"
                )
            receipts[case] = {
                "capture_id": capture["id"],
                "prompt_sha256": row["prompt_sha256"],
                "prompt_bytes": len(prompt.encode()),
            }
    return receipts


def child_environment(
    case: str, directory: Path, key: Path, *, deadline: float | None = None
) -> dict[str, str]:
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
    descriptor = source_descriptor()
    capture = json.loads((descriptor["root"] / case / "capture.json").read_text())
    env.update(
        PYTHONPATH=str(ROOT),
        VERIFIER_SEMANTIC_MODE="1",
        VERIFIER_SEMANTIC_KEY_PATH=str(key),
        VERIFIER_PAIRED_QUALIFICATION=case,
        PR_HEAD_SHA=capture["implementation_head"],
        VERIFIER_EVIDENCE_CAPTURE_DIR=str(directory),
        LANGCHAIN_SLOT_CONFIG=str(descriptor["slots_path"]),
        LANGCHAIN_MODEL_REGISTRY_CONFIG=str(ROOT / "config/model_registry.json"),
        VERIFIER_PAIRED_DESCRIPTOR_SHA256=descriptor["sha256"],
    )
    if deadline is None:
        deadline = time.monotonic() + load_packet()[1]["total_wall_seconds"]
    env["VERIFIER_PAIRED_PACKAGE_DEADLINE_MONOTONIC"] = repr(deadline)
    return env


def publish_case_outputs(
    private: Path, output: Path, case: str, credentials: tuple[str, ...]
) -> dict:
    """Publish only unchanged bytes that contain no configured credential.

    A killed parent leaves all unchecked child bytes outside the artifact root.
    Withheld records identify original bytes by hash, never claim redacted raw
    provenance, and never include provider exception text or credential values.
    """
    needles = set()
    for value in credentials:
        if value:
            needles.add(value.encode())
            needles.add(json.dumps(value, ensure_ascii=True)[1:-1].encode())
            needles.add(json.dumps(value, ensure_ascii=False)[1:-1].encode())
    published = {}
    for name in ("comparison.json", "diagnostic.log", "report.md"):
        source = private / case / name
        if not source.exists():
            continue
        if source.is_symlink() or not source.is_file():
            raise ValueError("child output is not a regular private file")
        raw = source.read_bytes()
        record = {"sha256": digest(raw), "bytes": len(raw), "status": "published_original"}
        if any(needle in raw for needle in needles):
            record.update(
                status="withheld_credentials",
                reason="configured provider credential in child output",
            )
            (output / case / name).unlink(missing_ok=True)
            (output / case / (name + ".withheld.json")).write_text(
                json.dumps(record, indent=2) + "\n"
            )
        else:
            (output / case / name).write_bytes(raw)
        published[name] = record
    return published


def retain_public_packet(output: Path, descriptor: dict, proposal: dict) -> dict:
    """Retain hash-checked public hidden members without uploading private files."""
    members = {
        "packet/" + name: _source_path(descriptor["root"], name)
        for name in {"PROPOSAL.json", "REVIEW.json"} | set(proposal["frozen_files"])
        if not (name == "build.py" and proposal["schema"] == "verify-public-api-paired-proposal/v1")
    }
    members.update(
        {
            "descriptor.json": DESCRIPTOR_PATH,
            "trial-policy.json": descriptor["policy_path"],
            "slots.json": descriptor["slots_path"],
        }
    )
    expected = {"packet/" + name: sha for name, sha in proposal["frozen_files"].items()}
    expected.update(
        {
            "packet/PROPOSAL.json": descriptor["proposal_sha256"],
            "packet/REVIEW.json": descriptor["review_sha256"],
            "descriptor.json": descriptor["sha256"],
            "trial-policy.json": descriptor["policy_sha256"],
            "slots.json": descriptor["slots_sha256"],
        }
    )
    inventory = {}
    with zipfile.ZipFile(
        output / "frozen-public-packet.zip", "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name, path in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            data = _source_bytes(path.parent, path.name)
            actual = digest(data)
            if actual != expected[name]:
                raise ValueError("public packet changed before archive retention")
            archive.writestr(info, data)
            inventory[name] = actual
    return {
        "sha256": digest((output / "frozen-public-packet.zip").read_bytes()),
        "entry_count": len(inventory),
        "entries_sha256": inventory,
        "assertion": "local_source_bytes_not_origin_authentication",
    }


def run(*, execute: bool) -> dict:
    started = time.monotonic()
    descriptor = source_descriptor()
    packet = descriptor["root"]
    cases = descriptor["cases"]
    proposal, policy = load_packet()
    deadline = started + policy["total_wall_seconds"]
    output = Path(os.environ["RUNNER_TEMP"]) / "verify-paired"
    private = Path(os.environ["RUNNER_TEMP"]) / "verify-paired-private"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {
        "schema": "verify-paired-invocation/v1",
        "status": "prepared",
        "proposal_sha256": descriptor["proposal_sha256"],
        "descriptor_sha256": descriptor["sha256"],
        "packet_source_head": proposal["source_head"],
        "policy": policy,
        "cases": proposal["cases"],
        "native_capacity_claim": False,
        "role_qualification_claim": False,
        "semantic_cli_started": False,
        "native_request_state": "not_started",
        "runtime_source": {
            "assertion": "local_source_bytes_not_origin_authentication",
            "files_sha256": {
                name: digest((ROOT / name).read_bytes())
                for name in (
                    "tools/run_verify_paired.py",
                    "tools/verify_paired_policy.py",
                    "scripts/langchain/pr_verifier.py",
                    "scripts/langchain/prompts/pr_evaluation.md",
                    "config/model_registry.json",
                    "requirements.lock",
                    "pyproject.toml",
                    descriptor["slots_path"].relative_to(ROOT).as_posix(),
                    descriptor["policy_path"].relative_to(ROOT).as_posix(),
                )
            },
            "dependencies": runtime_dependencies(),
        },
        "results": [],
        "output_publication": {},
    }
    key = private / ".semantic-key"
    credentials = ()
    private_owned = False
    try:
        for name in {"PROPOSAL.json", "REVIEW.json"} | {
            name for name in proposal["frozen_files"] if "/" not in name and name != "build.py"
        }:
            shutil.copyfile(packet / name, output / name)
        shutil.copyfile(descriptor["policy_path"], output / "trial-policy.json")
        shutil.copyfile(descriptor["slots_path"], output / "slots.json")
        shutil.copyfile(DESCRIPTOR_PATH, output / "descriptor.json")
        for case in cases:
            shutil.copytree(packet / case, output / case)
        receipt["public_packet_archive"] = retain_public_packet(output, descriptor, proposal)
        if not execute:
            return receipt
        if policy.get("execution_enabled") is not True or policy.get("review_status") != "reviewed":
            receipt.update(status="held", reason="trial policy awaits Core/executor review")
            return receipt
        if receipt["runtime_source"]["dependencies"]["matches_lock"] is not True:
            receipt.update(
                status="held",
                reason="installed SDK runtime differs from existing frozen requirements",
            )
            return receipt
        receipt["input_preflight"] = preflight_inputs(descriptor, proposal)
        private.mkdir(mode=0o700, parents=True, exist_ok=False)
        private_owned = True
        credentials = tuple(
            os.environ.get(name, "") for name in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE")
        )
        key.write_bytes(os.urandom(32))
        key.chmod(0o600)
        for case in cases:
            directory = private / case
            shutil.copytree(packet / case, directory)
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
            receipt["status"] = "in_progress"
            # A hard wall-time kill may prevent finally from running. Publish
            # only this safe unknown checkpoint before the private child starts.
            (output / "invocation.json").write_text(json.dumps(receipt, indent=2) + "\n")
            with (
                (directory / "comparison.json").open("wb") as stdout,
                (directory / "diagnostic.log").open("wb") as stderr,
            ):
                # Environment-derived paths are argv data; never interpret them as shell text.
                completed = subprocess.run(
                    argv,
                    shell=False,
                    cwd=ROOT,
                    env=child_environment(case, directory, key, deadline=deadline),
                    stdout=stdout,
                    stderr=stderr,
                    timeout=remaining,
                    check=False,
                )
            receipt["results"].append({"case": case, "returncode": completed.returncode})
            publication = publish_case_outputs(private, output, case, credentials)
            receipt["output_publication"][case] = publication
            withheld = any(row["status"] == "withheld_credentials" for row in publication.values())
            report = json.loads((directory / "comparison.json").read_text())
            semantic = report.get("semantic_acceptance") if isinstance(report, dict) else None
            trial = semantic.get("qualification_trial") if isinstance(semantic, dict) else None
            if not isinstance(trial, dict) or set(trial) != {
                "case",
                "policy",
                "attempted_native_requests",
                "native_capacity_claim",
                "role_qualification_claim",
                "attempted_physical_http_requests",
            }:
                raise ValueError("native trial counter record missing or malformed")
            attempted = trial.get("attempted_native_requests")
            limits = {"generation": 2, "count": 4, "metadata": 3}
            if (
                trial.get("case") != case
                or not isinstance(trial.get("policy"), dict)
                or json.dumps(trial["policy"], sort_keys=True) != json.dumps(policy, sort_keys=True)
                or trial.get("native_capacity_claim") is not False
                or trial.get("role_qualification_claim") is not False
                or type(trial.get("attempted_physical_http_requests")) is not int
                or not 0
                <= trial["attempted_physical_http_requests"]
                <= policy["max_physical_http_attempts"] // 2
                or not isinstance(attempted, dict)
                or set(attempted) != set(limits)
                or any(
                    type(value) is not int or not 0 <= value <= limits[name]
                    for name, value in attempted.items()
                )
                or trial["attempted_physical_http_requests"] > sum(attempted.values())
            ):
                raise ValueError("native trial counter record does not match bounded invocation")
            receipt["results"][-1]["attempted_native_requests"] = attempted
            physical = trial["attempted_physical_http_requests"]
            receipt["results"][-1]["attempted_physical_http_requests"] = physical
            receipt["native_request_state"] = (
                "attempts_recorded"
                if any(
                    sum(row.get("attempted_native_requests", {}).values())
                    for row in receipt["results"]
                )
                else "not_started"
            )
            if withheld:
                raise ValueError(
                    "credential-bearing child output withheld; no retry or replacement"
                )
            if completed.returncode:
                raise ValueError("semantic CLI failed; no retry or replacement")
            if attempted != limits or physical != policy["max_physical_http_attempts"] // 2:
                raise ValueError("native pair incomplete; partial request counters retained")
            arms = report.get("results", [])
            if (
                not isinstance(arms, list)
                or len(arms) != 2
                or any(
                    not isinstance(arm, dict) or arm.get("used_llm") is not True or arm.get("error")
                    for arm in arms
                )
            ):
                raise ValueError("native pair incomplete; retain raw output and stop")
        receipt["status"] = "completed_screen_only"
        return receipt
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
        receipt.update(status="held", reason=str(exc))
        return receipt
    finally:
        if private_owned:
            key.unlink(missing_ok=True)
            for case in cases:
                if (private / case).exists():
                    publication = publish_case_outputs(private, output, case, credentials)
                    receipt["output_publication"][case] = publication
                    if any(row["status"] == "withheld_credentials" for row in publication.values()):
                        receipt.update(
                            status="held",
                            reason="credential-bearing child output withheld; no retry or replacement",
                        )
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
