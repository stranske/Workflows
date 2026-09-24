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
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

RUN_SCHEMA_VERSION = "run-contract/v1"
DEFAULT_ARTIFACT_NAME = "run.json"
EMITTED_EVIDENCE_POLICY = "manifest-evidence-closure/v1"

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
    "tracked-variable/v1": "tracked-variable-v1.schema.json",
    "capability-bundle/v1": "capability-bundle-v1.schema.json",
    "mosaic-core/v1": "mosaic-core-v1.schema.json",
    "document-mirror/v1": "document-mirror-v1.schema.json",
    "output-substrate/v1": "output-substrate-v1.schema.json",
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


def _required_format_checker(*formats: str) -> FormatChecker:
    """Fail closed when optional JSON Schema format implementations are absent."""
    missing = [name for name in formats if name not in FormatChecker.checkers]
    if missing:
        raise RuntimeError(
            f"JSON Schema format checker(s) unavailable: {', '.join(missing)}; "
            "install jsonschema rfc3339-validator rfc3986-validator"
        )
    return FormatChecker(formats=formats)


def _validator_for_schema(schema_dir: Path, name: str) -> Draft202012Validator:
    schema = _load_schema(schema_dir, name)
    if name == "mosaic-core-v1.schema.json":
        # Explicitly request the checker so a missing rfc3339-validator dependency
        # fails instead of silently accepting malformed checked_at timestamps.
        return Draft202012Validator(schema, format_checker=_required_format_checker("date-time"))
    if name == "document-mirror-v1.schema.json":
        # Explicitly request URI/date-time checks so malformed resolver links and
        # catalog timestamps cannot pass as conformant.
        return Draft202012Validator(
            schema,
            format_checker=_required_format_checker("date-time", "uri"),
        )
    if name != "tracked-variable-v1.schema.json":
        return Draft202012Validator(schema)
    evidence = _load_schema(schema_dir, "evidence-object-v1.schema.json")
    registry = Registry().with_resources(
        [
            (schema["$id"], Resource.from_contents(schema)),
            (evidence["$id"], Resource.from_contents(evidence)),
        ]
    )
    return Draft202012Validator(schema, registry=registry)


def _check_document_page(document: Any, report: Report, prefix: str = "") -> None:
    """Check document identity details that JSON Schema cannot compare or parse."""
    if not isinstance(document, dict):
        return
    doc_ref = document.get("document_ref")
    locator = document.get("locator")
    if not isinstance(doc_ref, dict):
        return
    if (
        isinstance(locator, dict)
        and "page" in doc_ref
        and "page" in locator
        and doc_ref["page"] != locator["page"]
    ):
        report.fail("document_ref.page conflicts with locator.page", f"{prefix}document_ref/page")
    doc_key = doc_ref.get("doc_key")
    if isinstance(doc_key, str):
        as_of = doc_key.rsplit("/", 1)[-1]
        if as_of != "unknown":
            try:
                if date.fromisoformat(as_of).isoformat() != as_of:
                    raise ValueError("non-canonical date")
            except ValueError:
                report.fail(
                    "document_ref.doc_key as_of must be an ISO calendar date or unknown",
                    f"{prefix}document_ref/doc_key",
                )


def validate_evidence_objects(*, paths: list[Path], schema_dir: Path) -> Report:
    """Validate evidence-object/v1 fixtures without participant routing."""
    report = Report(repo="evidence-object/v1")
    validator = _validator_for_schema(schema_dir, "evidence-object-v1.schema.json")
    for path in paths:
        try:
            document = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.fail(f"cannot load evidence object {path}: {exc}", str(path))
            continue
        for err in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
            pointer = "/".join(str(p) for p in err.absolute_path)
            report.fail(err.message, f"{path}:/{pointer}")
        _check_document_page(document, report, f"{path}:/")
    return report


def validate_tracked_variables(*, paths: list[Path], schema_dir: Path) -> Report:
    """Validate one or more tracked-variable/v1 JSON files against the schema."""
    report = Report(repo="tracked-variable/v1")
    validator = _validator_for_schema(schema_dir, "tracked-variable-v1.schema.json")
    for path in paths:
        try:
            document = _load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            report.fail(f"cannot load tracked variable {path}: {exc}", str(path))
            continue
        for err in sorted(
            validator.iter_errors(document),
            key=lambda e: list(e.absolute_path),
        ):
            report.fail(err.message, "/".join(str(p) for p in err.absolute_path))
        if isinstance(document, dict):
            _check_document_page(document.get("evidence"), report, "evidence/")
    return report


def validate_mirror_manifests(*, paths: list[Path], schema_dir: Path) -> Report:
    """Validate one or more document-mirror/v1 JSON files against the schema."""
    report = Report(repo="document-mirror/v1")
    validator = _validator_for_schema(schema_dir, "document-mirror-v1.schema.json")
    for path in paths:
        try:
            document = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.fail(f"cannot load mirror manifest {path}: {exc}", str(path))
            continue
        for err in sorted(
            validator.iter_errors(document),
            key=lambda e: list(e.absolute_path),
        ):
            pointer = "/".join(str(p) for p in err.absolute_path)
            report.fail(err.message, f"{path}:/{pointer}")
    return report


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
        validator = _validator_for_schema(schema_dir, INGEST_SCHEMA_FILES[token])
        errs = [e.message for e in validator.iter_errors(document)]
        if not errs:
            # Matched an ingested schema -> conformant.
            _scan_unsafe(document, report)
            if token == "evidence-object/v1":
                _check_document_page(document, report)
            elif token == "tracked-variable/v1" and isinstance(document, dict):
                _check_document_page(document.get("evidence"), report, "evidence/")
            return report
        per_schema_errors[token] = errs

    # Matched none of the ingested schemas: report the closest (fewest errors).
    best = min(per_schema_errors.items(), key=lambda kv: len(kv[1]))
    for msg in best[1]:
        report.fail(f"ingested-as-{best[0]}: {msg}")
    return report


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 of file bytes without loading an artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_evidence_path(
    run_dir: Path, artifact: dict[str, Any], report: Report, index: int
) -> Path | None:
    """Resolve one manifest evidence path without following a symlink or escaping its run."""
    path_value = artifact.get("path")
    path_label = f"manifest.artifacts[{index}].path"
    if not isinstance(path_value, str) or not path_value or "\\" in path_value:
        report.fail("evidence artifact path must be a non-empty relative POSIX path", path_label)
        return None
    relative = PurePosixPath(path_value)
    if relative.is_absolute() or ".." in relative.parts:
        report.fail("evidence artifact path must not be absolute or traverse parents", path_label)
        return None

    candidate = run_dir.joinpath(*relative.parts)
    try:
        # Reject every symlink component, including one that happens to point
        # back inside the run directory: manifests describe regular artifacts.
        current = run_dir
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                report.fail("evidence artifact path must not traverse a symlink", path_label)
                return None
        resolved_run_dir = run_dir.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        report.fail(f"cannot resolve evidence artifact: {exc}", path_label)
        return None
    if not resolved_candidate.is_relative_to(resolved_run_dir):
        report.fail("evidence artifact path escapes the run directory", path_label)
        return None
    if not candidate.is_file():
        report.fail("evidence artifact must be an existing regular file", path_label)
        return None
    return candidate


def _validate_manifest_evidence_closure(
    *,
    envelope: dict[str, Any],
    manifest: dict[str, Any] | None,
    run_json: Path | None,
    schema_dir: Path,
    report: Report,
) -> None:
    """Validate opt-in evidence files and their two-way envelope closure."""
    if not isinstance(manifest, dict):
        report.fail("emitted_evidence_policy requires an artifact manifest object", "manifest")
        return
    if run_json is None:
        report.fail("emitted_evidence_policy requires run_json artifact context", "run_json")
        return
    run_dir = run_json.parent
    if not run_dir.is_dir():
        report.fail("run_json parent is not an existing artifact directory", "run_json")
        return

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        report.fail("manifest artifacts must be a list for evidence closure", "manifest.artifacts")
        return

    validator = _validator_for_schema(schema_dir, "evidence-object-v1.schema.json")
    evidence_ids: list[str] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            continue  # The manifest schema already reports this malformed entry.
        name = artifact.get("name")
        if artifact.get("kind") != "evidence" or not (
            isinstance(name, str) and name.startswith("evidence-") and name.endswith(".json")
        ):
            continue
        path = _safe_evidence_path(run_dir, artifact, report, index)
        if path is None:
            continue
        expected_hash = artifact.get("sha256")
        if not isinstance(expected_hash, str):
            report.fail(
                "evidence artifact sha256 must be a string", f"manifest.artifacts[{index}].sha256"
            )
        else:
            try:
                actual_hash = _sha256_file(path)
            except OSError as exc:
                report.fail(f"cannot hash evidence artifact: {exc}", str(path))
                continue
            if actual_hash != expected_hash:
                report.fail("evidence artifact SHA-256 does not match manifest bytes", str(path))

        try:
            evidence = _load_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            report.fail(f"cannot load evidence artifact: {exc}", str(path))
            continue
        for err in sorted(validator.iter_errors(evidence), key=lambda err: list(err.absolute_path)):
            pointer = "/".join(str(part) for part in err.absolute_path)
            # jsonschema error messages may echo the invalid instance, including
            # confidential excerpts. Reports are published to PR comments.
            report.fail(
                f"evidence schema validation failed ({err.validator})", f"{path}:/{pointer}"
            )
        _check_document_page(evidence, report, f"{path}:/")
        if isinstance(evidence, dict) and isinstance(evidence.get("evidence_id"), str):
            evidence_ids.append(evidence["evidence_id"])

    duplicates = sorted({item for item in evidence_ids if evidence_ids.count(item) > 1})
    for evidence_id in duplicates:
        report.fail(
            f"duplicate evidence_id '{evidence_id}' in emitted evidence artifacts",
            "manifest.artifacts",
        )

    refs = envelope.get("evidence_refs", [])
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        report.fail("evidence_refs must be a list of strings for evidence closure", "evidence_refs")
        return
    duplicate_refs = sorted({item for item in refs if refs.count(item) > 1})
    for evidence_id in duplicate_refs:
        report.fail(f"duplicate evidence_ref '{evidence_id}'", "evidence_refs")
    emitted = set(evidence_ids)
    referenced = set(refs)
    for evidence_id in sorted(referenced - emitted):
        report.fail(
            f"evidence_ref '{evidence_id}' has no emitted evidence artifact", "evidence_refs"
        )
    for evidence_id in sorted(emitted - referenced):
        report.fail(
            f"emitted evidence_id '{evidence_id}' is absent from evidence_refs", "evidence_refs"
        )


def validate_envelope(
    *,
    envelope: dict[str, Any],
    schema_dir: Path,
    registry: dict[str, Any],
    repo: str,
    manifest: dict[str, Any] | None,
    run_json: Path | None = None,
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
        artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []
        if not isinstance(artifacts, list):
            artifacts = []
        by_id = {a.get("artifact_id"): a for a in artifacts if isinstance(a, dict)}
        outputs = envelope.get("outputs", {})
        artifact_ids = outputs.get("artifact_ids", []) if isinstance(outputs, dict) else []
        for art_id in artifact_ids if isinstance(artifact_ids, list) else []:
            art = by_id.get(art_id)
            if art is None:
                report.fail(f"artifact_id '{art_id}' not in manifest", "outputs.artifact_ids")
            elif not art.get("sha256"):
                report.fail(f"manifest artifact '{art_id}' missing sha256", "manifest.artifacts")

    # 7. Only the explicit policy activates filesystem evidence validation. This
    # keeps legacy/disabled participants independent of local artifact layout.
    policy = entry.get("emitted_evidence_policy")
    if policy is not None and policy != EMITTED_EVIDENCE_POLICY:
        report.fail("unknown emitted_evidence_policy", "emitted_evidence_policy")
    elif policy == EMITTED_EVIDENCE_POLICY:
        _validate_manifest_evidence_closure(
            envelope=envelope,
            manifest=manifest,
            run_json=run_json,
            schema_dir=schema_dir,
            report=report,
        )

    return report


def _find_participant(registry: dict[str, Any], repo: str) -> dict[str, Any] | None:
    """Look up a participant by repo in the registry. Returns None if not found."""
    return _find_entry(registry, repo)


def _is_missing_envelope_a_failure(entry: dict[str, Any] | None) -> bool:
    """Decide whether a missing envelope should fail (True) or skip (False).

    An emitting or conformant participant MUST have an envelope; all others
    (absent, candidate, none, planned) are opt-in skip.
    """
    return entry is not None and entry.get("status") in EMITTING_STATUSES


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
    entry = _find_participant(registry, repo)
    report = Report(repo=repo, role=entry.get("role", "") if entry else "")

    if _is_missing_envelope_a_failure(entry):
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
    parser.add_argument("run_json", type=Path, nargs="?", default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--registry", type=Path)
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "contracts" / "schemas",
    )
    parser.add_argument("--repo")
    parser.add_argument("--warn-only", action="store_true")
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument(
        "--self-smoke",
        action="store_true",
        help="Run an offline self-smoke over bundled fixtures and exit.",
    )
    parser.add_argument(
        "--evidence-objects",
        type=Path,
        nargs="+",
        default=None,
        help="Validate one or more evidence-object/v1 JSON files against the schema.",
    )
    parser.add_argument(
        "--tracked-variables",
        type=Path,
        nargs="+",
        default=None,
        help="Validate one or more tracked-variable/v1 JSON files against the schema.",
    )
    parser.add_argument(
        "--mirror-manifest",
        type=Path,
        nargs="+",
        default=None,
        help="Validate one or more document-mirror/v1 JSON catalog files against the schema.",
    )
    args = parser.parse_args(argv)

    modes = [args.self_smoke, args.evidence_objects, args.tracked_variables, args.mirror_manifest]
    if sum(bool(mode) for mode in modes) > 1:
        parser.error(
            "--self-smoke, --evidence-objects, --tracked-variables and --mirror-manifest are mutually exclusive"
        )

    standalone_schema_mode = args.evidence_objects or args.tracked_variables or args.mirror_manifest

    # Standalone schema validation does not consult participant routing. Keep
    # that context mandatory for the existing envelope and self-smoke modes.
    if args.self_smoke or not standalone_schema_mode:
        missing = [flag for flag in ("--registry", "--repo") if getattr(args, flag[2:]) is None]
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")

    if args.self_smoke:
        return _self_smoke(args.schema_dir, args.registry)

    if args.evidence_objects:
        report = validate_evidence_objects(
            paths=list(args.evidence_objects),
            schema_dir=args.schema_dir,
        )
        label = "evidence-object/v1"
    elif args.tracked_variables:
        report = validate_tracked_variables(
            paths=list(args.tracked_variables),
            schema_dir=args.schema_dir,
        )
        label = "tracked-variable/v1"
    elif args.mirror_manifest:
        report = validate_mirror_manifests(
            paths=list(args.mirror_manifest),
            schema_dir=args.schema_dir,
        )
        label = "document-mirror/v1"
    else:
        report = None

    if report is not None:
        path_count = len(
            args.evidence_objects or args.tracked_variables or args.mirror_manifest or []
        )
        if report.conformant:
            print(f"{label}: {path_count} file(s) conform to schema")
        else:
            print(
                f"{label}: {len(report.violations)} conformance violation(s):",
                file=sys.stderr,
            )
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
                fh.write(f"conformant={'true' if report.conformant else 'false'}\n")
        return 0 if (report.conformant or args.warn_only) else 1

    registry = _load_json(args.registry)

    if args.run_json is None:
        print(
            "ERROR: run_json path is required unless exactly one of --evidence-objects, --tracked-variables or --mirror-manifest is set",
            file=sys.stderr,
        )
        return 2

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
            print(f"ERROR: cannot load artifact manifest {args.manifest}: {exc}", file=sys.stderr)
            return 2
        report = validate_envelope(
            envelope=envelope,
            schema_dir=args.schema_dir,
            registry=registry,
            repo=args.repo,
            manifest=manifest,
            run_json=args.run_json,
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
    # Load EVERY bundled schema (must be valid Draft 2020-12). Discovering them
    # rather than naming three means a schema added to the directory is checked
    # the day it lands; the previous hardcoded triple silently skipped
    # tracked-variable-v1 and capability-bundle-v1.
    schema_names = sorted(path.name for path in schema_dir.glob("*.schema.json"))
    if not schema_names:
        print(
            f"FAIL schema dir {schema_dir}: no *.schema.json files found; "
            "self-smoke cannot validate schemas"
        )
        return 1
    missing = sorted(set(INGEST_SCHEMA_FILES.values()) - set(schema_names))
    if missing:
        print(f"FAIL schema dir {schema_dir}: missing registered schemas: {', '.join(missing)}")
        return 1
    for name in schema_names:
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
        # Unsafe raw payload fixtures must fail without echoing sensitive values.
        for inv in (
            "missing_cost.json",
            "unsafe_rows_inline.json",
            "unsafe_prompt_inline.json",
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
