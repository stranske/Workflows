#!/usr/bin/env python3
"""Validate a research-backplane run envelope against run-contract/v1.

Mirrors scripts/langsmith_fleet.py: offline, deterministic, no cloud key.
Exits non-zero on any conformance violation (unless --warn-only).

Role-aware (config/backplane_participants.json ``role``):

- ``producer`` / ``bridge``: validate full run-contract/v1 emission (required
  shared fields + the entry's ``required_sections`` + the manifest cross-check).
- ``consumer``: validate ONLY the satellite schemas the entry lists under
  ``ingests`` (the input is treated as an ingested object, e.g. an
  evidence-object/v1). An active consumer is failed for a missing declared
  input, not for failing to emit a producer run envelope.

Opt-in: a repo absent from the registry, or with ``status`` of ``none`` /
``candidate``, is a no-op SKIP (success). This is the one deliberate difference
from the fleet validator.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

RUN_SCHEMA_VERSION = "run-contract/v1"
DEFAULT_ARTIFACT_NAME = "run.json"

# Statuses that mean "the contract does not (yet) apply" -> opt-in skip.
SKIP_STATUSES = (None, "none", "candidate")

# Statuses where a producer/bridge is ACTIVELY emitting a run envelope, so a
# MISSING run.json is a real regression rather than a not-yet-wired no-op. The
# lifecycle is planned -> emitting -> conformant; a "planned" producer has not
# wired its emitter yet, so an absent envelope is still an opt-in skip for it.
EMITTING_STATUSES = ("emitting", "conformant")

# Map an ``ingests`` token to the schema file a consumer validates against.
INGEST_SCHEMA_FILES = {
    "run-contract/v1": "run-contract-v1.schema.json",
    "artifact-manifest/v1": "artifact-manifest-v1.schema.json",
    "evidence-object/v1": "evidence-object-v1.schema.json",
}
# Tokens that are convention-only (no JSON Schema to load); accepted as declared
# ingest surfaces but not schema-validated here.
INGEST_CONVENTION_ONLY = ("identity-map-conventions",)

# Optional run-contract/v1 sections a registry entry may mark required.
KNOWN_SECTIONS = (
    "cost",
    "latency",
    "warnings",
    "data_quality",
    "evidence_refs",
    "identity_refs",
)

# Sections where an EMPTY value is a meaningful "ran, nothing to report" signal
# (a clean run legitimately has zero warnings / zero evidence / zero ids), so
# only ABSENCE of the key is a violation. For the rest (cost/latency/
# data_quality) an empty value is treated as "not populated" and fails.
SECTIONS_EMPTY_OK = ("warnings", "evidence_refs", "identity_refs")

# Field names that must never carry raw payloads inline (publish refs instead).
UNSAFE_RAW_FIELDS = (
    "prompt",
    "raw_prompt",
    "raw_output",
    "model_output",
    "rows",
    "result_rows",
    "document_text",
    "pii",
)


@dataclass
class Violation:
    message: str
    path: str = ""


@dataclass
class Report:
    repo: str
    role: str = ""
    conformant: bool = True
    skipped: bool = False
    violations: list[Violation] = field(default_factory=list)

    def fail(self, message: str, path: str = "") -> None:
        self.conformant = False
        self.violations.append(Violation(message=message, path=path))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _load_schema(schema_dir: Path, name: str) -> dict[str, Any]:
    return _load_json(schema_dir / name)


def _find_entry(registry: dict[str, Any], repo: str) -> dict[str, Any] | None:
    for entry in registry.get("participants", []):
        if entry.get("repo") == repo:
            return entry
    return None


def _scan_unsafe(obj: Any, report: Report, prefix: str = "") -> None:
    """Reject inline raw payloads anywhere in the envelope."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{prefix}.{key}" if prefix else key
            if key.lower() in UNSAFE_RAW_FIELDS and value not in (None, "", [], {}):
                report.fail(f"unsafe raw payload field '{key}' inlined", here)
            _scan_unsafe(value, report, here)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _scan_unsafe(value, report, f"{prefix}[{i}]")


def _validate_consumer(
    *,
    document: Any,
    schema_dir: Path,
    entry: dict[str, Any],
    report: Report,
) -> Report:
    """Consumer role: validate the document against ONE of the ingested schemas.

    A consumer never emits a run envelope, so it is not required to satisfy the
    full run-contract. It only proves the artifact it INGESTS conforms to the
    satellite schema it declares.
    """
    ingests = entry.get("ingests", []) or []
    if not ingests:
        report.fail(
            f"consumer {report.repo} declares no 'ingests' schemas to validate",
            "ingests",
        )
        return report

    # Try each declared schema; the document conforms if it matches at least one
    # of the ingested schema shapes (e.g. an evidence-object/v1 object).
    unknown = [
        t for t in ingests if t not in INGEST_SCHEMA_FILES and t not in INGEST_CONVENTION_ONLY
    ]
    for tok in unknown:
        report.fail(f"unknown ingest schema token '{tok}'", "ingests")

    schema_tokens = [t for t in ingests if t in INGEST_SCHEMA_FILES]
    if not schema_tokens:
        # Only convention-only ingests (e.g. identity-map-conventions): nothing
        # to schema-validate; presence of a declared ingest is enough.
        return report

    per_schema_errors: dict[str, list[str]] = {}
    for token in schema_tokens:
        schema = _load_schema(schema_dir, INGEST_SCHEMA_FILES[token])
        errs = [e.message for e in Draft202012Validator(schema).iter_errors(document)]
        if not errs:
            # Matched an ingested schema -> conformant.
            _scan_unsafe(document, report)
            return report
        per_schema_errors[token] = errs

    # Matched none of the ingested schemas: report the closest (fewest errors).
    best = min(per_schema_errors.items(), key=lambda kv: len(kv[1]))
    for msg in best[1]:
        report.fail(f"ingested-as-{best[0]}: {msg}")
    return report


def validate_envelope(
    *,
    envelope: dict[str, Any],
    schema_dir: Path,
    registry: dict[str, Any],
    repo: str,
    manifest: dict[str, Any] | None,
) -> Report:
    report = Report(repo=repo)

    # 1. Opt-in gate: not a participant (or status none/candidate) -> skip.
    entry = _find_entry(registry, repo)
    if entry is None or entry.get("status") in SKIP_STATUSES:
        report.skipped = True
        return report

    role = entry.get("role", "producer")
    report.role = role

    # 1b. Consumer role: validate only the ingested schema(s), not full emission.
    if role == "consumer":
        return _validate_consumer(
            document=envelope, schema_dir=schema_dir, entry=entry, report=report
        )

    # --- producer / bridge: full run-contract/v1 emission validation ---

    # 2. Schema conformance against run-contract/v1.
    run_schema = _load_schema(schema_dir, "run-contract-v1.schema.json")
    for err in sorted(
        Draft202012Validator(run_schema).iter_errors(envelope),
        key=lambda e: list(e.absolute_path),
    ):
        report.fail(err.message, "/".join(str(p) for p in err.absolute_path))

    if envelope.get("schema_version") != RUN_SCHEMA_VERSION:
        report.fail(f"schema_version must be '{RUN_SCHEMA_VERSION}'", "schema_version")

    # 3. Registry-required sections present (role-aware: a tool is never failed
    #    for omitting a section that is out of its declared role).
    for section in entry.get("required_sections", []):
        if section not in KNOWN_SECTIONS:
            report.fail(f"registry lists unknown required section '{section}'")
            continue
        present = section in envelope and envelope.get(section) is not None
        if not present:
            report.fail(f"registry requires section '{section}' for {repo} (key absent)", section)
        elif section not in SECTIONS_EMPTY_OK and envelope.get(section) in ("", [], {}):
            # cost/latency/data_quality: present-but-empty == not populated.
            report.fail(f"registry requires a populated '{section}' for {repo}", section)

    # 4. No inline raw payloads (PII / prompts / rows / full output).
    _scan_unsafe(envelope, report)

    # 5. Identity refs use the canonical-ID convention (schema enforces the
    #    pattern; here we double-check non-empty type when required).
    for ref in envelope.get("identity_refs", []) or []:
        if not isinstance(ref, str) or ":" not in ref:
            report.fail(f"identity_ref '{ref}' is not a canonical <type>:<id>", "identity_refs")

    # 6. Manifest cross-check: every emitted artifact_id is in the manifest
    #    with a sha256, and the manifest itself validates.
    if manifest is not None:
        manifest_schema = _load_schema(schema_dir, "artifact-manifest-v1.schema.json")
        for err in Draft202012Validator(manifest_schema).iter_errors(manifest):
            report.fail(f"manifest: {err.message}", "/".join(str(p) for p in err.absolute_path))
        by_id = {a.get("artifact_id"): a for a in manifest.get("artifacts", [])}
        for art_id in envelope.get("outputs", {}).get("artifact_ids", []) or []:
            art = by_id.get(art_id)
            if art is None:
                report.fail(f"artifact_id '{art_id}' not in manifest", "outputs.artifact_ids")
            elif not art.get("sha256"):
                report.fail(f"manifest artifact '{art_id}' missing sha256", "manifest.artifacts")

    # 7. Evidence presence is handled by the required_sections loop above, where
    #    'evidence_refs' is empty-OK (a clean run may attribute nothing). When
    #    evidence objects are provided inline/alongside, validate each against
    #    evidence-object/v1 (the gate resolves & validates referenced objects).

    return report


def missing_envelope_report(registry: dict[str, Any], repo: str, run_json: Path) -> Report:
    """Decide what a MISSING run envelope means for ``repo``.

    The caller's ``emit-reference-run`` job intentionally produces nothing until
    a repo wires its emitter ("the conformance gate will skip (opt-in)"), and
    the registry lifecycle is planned -> emitting -> conformant. So an absent
    envelope is a clean opt-in SKIP for every repo EXCEPT a participant that has
    already reached an emitting/conformant status -- for those a vanished input
    artifact is a genuine regression and must fail. This keeps the opt-in
    contract honest (a non-participant, candidate, or not-yet-emitting producer
    is never failed just for lacking an envelope) without silencing a real
    regression in an active participant.
    """
    entry = _find_entry(registry, repo)
    report = Report(repo=repo, role=entry.get("role", "") if entry else "")
    is_active_participant = entry is not None and entry.get("status") in EMITTING_STATUSES
    if is_active_participant:
        assert entry is not None
        report.fail(
            f"{repo} is an active backplane participant "
            f"(role={entry.get('role')!r}, status={entry.get('status')!r}) "
            f"but no run envelope was found "
            f"at {run_json}",
            str(run_json),
        )
    else:
        report.skipped = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_json", type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--schema-dir", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--warn-only", action="store_true")
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument(
        "--self-smoke",
        action="store_true",
        help="Run an offline self-smoke over bundled fixtures and exit.",
    )
    args = parser.parse_args(argv)

    if args.self_smoke:
        return _self_smoke(args.schema_dir, args.registry)

    registry = _load_json(args.registry)

    try:
        envelope = _load_json(args.run_json)
    except FileNotFoundError:
        # No emitted envelope. Opt-in: this is a no-op SKIP for every repo
        # except an actively-emitting producer (see missing_envelope_report),
        # matching the caller stub's "the conformance gate will skip (opt-in)".
        envelope = None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load run envelope: {exc}", file=sys.stderr)
        return 2

    if envelope is None:
        report = missing_envelope_report(registry, args.repo, args.run_json)
    else:
        try:
            manifest = _load_json(args.manifest) if args.manifest else None
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot load artifact manifest: {exc}", file=sys.stderr)
            return 2
        report = validate_envelope(
            envelope=envelope,
            schema_dir=args.schema_dir,
            registry=registry,
            repo=args.repo,
            manifest=manifest,
        )

    if report.skipped:
        print(f"{args.repo}: not a (yet-emitting) backplane participant (opt-in); skipping")
    elif report.conformant:
        print(f"{args.repo}: run envelope conforms to {RUN_SCHEMA_VERSION}")
    else:
        print(f"{args.repo}: {len(report.violations)} conformance violation(s):", file=sys.stderr)
        for v in report.violations:
            print(f"  - [{v.path}] {v.message}", file=sys.stderr)

    if args.report_json:
        args.report_json.write_text(
            json.dumps(
                {
                    "repo": report.repo,
                    "role": report.role,
                    "conformant": report.conformant,
                    "skipped": report.skipped,
                    "violations": [
                        {"path": v.path, "message": v.message} for v in report.violations
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    if args.github_output:
        with args.github_output.open("a") as fh:
            ok = report.conformant or report.skipped
            fh.write(f"conformant={'true' if ok else 'false'}\n")

    if report.skipped or report.conformant:
        return 0
    return 0 if args.warn_only else 1


def _self_smoke(schema_dir: Path, registry_path: Path) -> int:
    """Offline self-check: schemas load + valid/invalid fixtures behave.

    Looks for fixtures next to the repo's tests/fixtures/backplane/. Prints a
    PASS/FAIL line per case and returns non-zero if any case is unexpected.
    """
    registry = _load_json(registry_path)
    # Load all three schemas (must be valid Draft 2020-12).
    for name in (
        "run-contract-v1.schema.json",
        "artifact-manifest-v1.schema.json",
        "evidence-object-v1.schema.json",
    ):
        schema = _load_schema(schema_dir, name)
        Draft202012Validator.check_schema(schema)
        print(f"PASS schema loads + valid Draft202012: {name}")

    fx = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "backplane"
    cases = []
    if fx.is_dir():
        valid_run = fx / "valid_run.json"
        valid_manifest = fx / "valid_manifest.json"
        if valid_run.is_file():
            cases.append(
                (
                    valid_run,
                    valid_manifest if valid_manifest.is_file() else None,
                    "stranske/Pension-Data",
                    True,
                )
            )
        for inv in (
            "missing_cost.json",
            "unsafe_rows_inline.json",
            "artifact_not_in_manifest.json",
            "bad_identity_ref.json",
        ):
            p = fx / inv
            if p.is_file():
                mani = (
                    valid_manifest
                    if (inv == "artifact_not_in_manifest.json" and valid_manifest.is_file())
                    else None
                )
                cases.append((p, mani, "stranske/Pension-Data", False))

    ok = True
    for path, mani_path, repo, expect_pass in cases:
        envelope = _load_json(path)
        manifest = _load_json(mani_path) if mani_path else None
        report = validate_envelope(
            envelope=envelope,
            schema_dir=schema_dir,
            registry=registry,
            repo=repo,
            manifest=manifest,
        )
        passed = report.conformant or report.skipped
        good = passed == expect_pass
        ok = ok and good
        verdict = "PASS" if good else "FAIL"
        want = "conform" if expect_pass else "reject"
        print(
            f"{verdict} fixture {path.name}: expected {want}, "
            f"got {'conform' if passed else 'reject'}"
        )

    if not cases:
        print("NOTE: no fixtures found; schema-only self-smoke.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
