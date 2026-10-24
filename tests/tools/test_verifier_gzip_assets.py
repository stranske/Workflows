"""Typed gzip evidence is a bounded derived view, never a substitute Git patch."""

import copy
import gzip
import hashlib
import json

import pytest
from scripts.langchain import pr_verifier
from tools.verifier_capture_obligation_manifest import (
    _full_patch_file_records,
    build_capture_obligation_manifest,
)
from tools.verifier_gzip_assets import CODEC, SCHEMA, decode_gzip_text, verified_assets

IDENTITY = "- Repository: a/b\n- Target commit: `" + "a" * 40 + "`\n\n"


def asset(tmp_path, name="docs/verification/é.log.gz", text="exact π proof\r\n"):
    raw = gzip.compress(text.encode(), mtime=0)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    patch = (
        f"diff --git a/{name} b/{name}\nnew file mode 100644\n"
        f"index 0000000..{blob}\nBinary files /dev/null and b/{name} differ\n"
    ).encode()
    span = _full_patch_file_records(patch)[0]

    def sha(b):
        return hashlib.sha256(b).hexdigest()

    row = {
        "schema": SCHEMA,
        "codec": CODEC,
        "source": name,
        "input_id": "gzip_asset:" + hashlib.sha256(name.encode()).hexdigest(),
        "repository": "a/b",
        "evaluated_sha": "a" * 40,
        "change_kind": "added",
        "necessity": "unknown",
        "patch_sha256": span["sha256"],
        "status": "captured",
        "mode": "100644",
        "git_blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "raw_sha256": sha(raw),
        "text_sha256": sha(text.encode()),
        "raw_bytes": len(raw),
        "text_bytes": len(text.encode()),
    }
    (tmp_path / (sha(raw) + ".gz")).write_bytes(raw)
    (tmp_path / (sha(text.encode()) + ".txt")).write_bytes(text.encode())
    coverage = {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "gzip_asset_binding": {"repository": "a/b", "evaluated_sha": "a" * 40},
        "gzip_asset_sources": [row],
        "changed_code_sources": [
            {
                "source": name,
                "status": "unavailable",
                "included_chars": len(patch),
                "total_chars": len(patch),
            }
        ],
        "acceptance_sources": [
            {"source": "issue:1", "status": "included", "included_chars": 1, "total_chars": 1}
        ],
        "acceptance_evidence_sources": [],
        "full_diff_artifact": {},
    }
    return patch, coverage, row


@pytest.mark.parametrize("text", ["plain", "π\r\nexact", ""])
def test_decode_exact(text):
    assert decode_gzip_text(gzip.compress(text.encode())) == text.encode()


@pytest.mark.parametrize(
    "kind",
    ["crc", "truncated", "trailing", "multimember", "bomb", "invalid_utf8", "nul", "raw_bound"],
)
def test_bad_gzip(kind):
    raw = gzip.compress(b"x" * 100)
    kwargs = {}
    if kind == "crc":
        raw = raw[:-8] + bytes([raw[-8] ^ 1]) + raw[-7:]
    if kind == "truncated":
        raw = raw[:-1]
    if kind == "trailing":
        raw += b"junk"
    if kind == "multimember":
        raw += gzip.compress(b"next")
    if kind == "bomb":
        kwargs["max_text"] = 99
    if kind == "raw_bound":
        kwargs["max_raw"] = 1
    if kind == "invalid_utf8":
        raw = gzip.compress(b"\xff")
    if kind == "nul":
        raw = gzip.compress(b"\0")
    with pytest.raises(ValueError):
        decode_gzip_text(raw, **kwargs)


def test_exact_bound():
    assert decode_gzip_text(gzip.compress(b"x" * 100), max_text=100) == b"x" * 100


def test_authentic_views_clear_only_their_binary_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    patch, coverage, row = asset(tmp_path)
    assert (
        verified_assets(coverage, tmp_path, patch)[row["source"]]["text"]
        == b"exact \xcf\x80 proof\r\n"
    )
    context = IDENTITY + (
        "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\n"
    )
    manifest = build_capture_obligation_manifest(context, full_diff_bytes=patch)
    assert not any(
        "binary" in gap or gap.endswith(":unavailable") for gap in manifest["gaps"]
    ), manifest["gaps"]
    prompts = pr_verifier.build_prompt_inputs(context, patch.decode(), lossless=True)
    assert prompts.coverage.files[0].status == "complete"
    assert "not a Git patch" in prompts.diff_block and "exact π proof" in prompts.diff_block
    assert patch.decode().strip() in prompts.diff_block
    functional = b"diff --git a/src/data.bin b/src/data.bin\nnew file mode 100644\nindex 0000000..1234567\nBinary files /dev/null and b/src/data.bin differ\n"
    assert (
        pr_verifier.build_prompt_inputs(context, (patch + functional).decode(), lossless=True)
        .coverage.files[-1]
        .status
        == "omitted"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("git_blob_sha", "0" * 40),
        ("raw_sha256", "0" * 64),
        ("text_sha256", "0" * 64),
        ("evaluated_sha", "b" * 40),
        ("patch_sha256", "0" * 64),
        ("change_kind", "modified"),
        ("mode", "120000"),
    ],
)
def test_identity_tampering_refused(tmp_path, field, value):
    patch, coverage, row = asset(tmp_path)
    row[field] = value
    with pytest.raises((ValueError, OSError)):
        verified_assets(coverage, tmp_path, patch)


def test_duplicate_paths_refused_content_reuse_allowed(tmp_path):
    a, coverage, row = asset(tmp_path, name="docs/verification/a.log.gz")
    b, other, _ = asset(tmp_path, name="docs/verification/b.log.gz")
    coverage["gzip_asset_sources"] += other["gzip_asset_sources"]
    assert len(verified_assets(coverage, tmp_path, a + b)) == 2
    coverage["gzip_asset_sources"].append(copy.deepcopy(row))
    with pytest.raises(ValueError, match="duplicate"):
        verified_assets(coverage, tmp_path, a + b)


def test_sidecar_tampering_and_symlinks(tmp_path):
    patch, coverage, row = asset(tmp_path)
    target = tmp_path / (row["text_sha256"] + ".txt")
    target.write_text("changed")
    with pytest.raises(ValueError):
        verified_assets(coverage, tmp_path, patch)
    target.unlink()
    target.symlink_to(tmp_path / (row["raw_sha256"] + ".gz"))
    with pytest.raises(ValueError):
        verified_assets(coverage, tmp_path, patch)


@pytest.mark.parametrize("failure", [None, "required_asset", "required_artifact"])
def test_expanded_evaluate_public_cli_native_admission(tmp_path, monkeypatch, capsys, failure):
    """Real CLI/capture/screen/count path; only SDK client is a unit-only stub."""
    from types import SimpleNamespace

    from tests.scripts.conftest import synthetic_verifier_capacity_contract
    from tests.scripts.verifier_capacity_fakes import with_capacity

    synthetic_verifier_capacity_contract.__wrapped__(monkeypatch)

    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "0")
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    patch, coverage, row = asset(tmp_path)
    coverage["acceptance_source_discovery"] = {"required": False, "status": "included"}
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(patch.decode()),
    }
    coverage["acceptance_evidence_sources"] = [
        {
            "source": "artifacts",
            "channel": "artifacts",
            "status": "unavailable",
            "failure_kinds": ["transport"],
        }
    ]
    coverage["acceptance_evidence_sources"].append(
        {
            "source": "comment:1",
            "channel": "comments",
            "status": "included",
            "included_chars": 25,
            "total_chars": 25,
        }
    )
    criterion = "Provide test evidence in a PR comment or workflow artifacts."
    if failure == "required_artifact":
        criterion += " The reviewer must upload a workflow artifact."
    if failure == "required_asset":
        row["necessity"] = "required"
        (tmp_path / (row["raw_sha256"] + ".gz")).unlink()
    context = IDENTITY + (
        "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\nNo failures.\n\n"
        "## Plan sources (scope, tasks, acceptance)\n#### Acceptance criteria\n- "
        + criterion
        + "\n\n"
        "## Acceptance evidence\n- Overall retrieval status: **present**\n- PR body: **present**\n- PR comments: **present**\n- Referenced workflow artifacts: **unavailable**\n"
        "### Bounded PR comments\nReal retained test proof.\n\n## PR Diff Summary\n- Files changed: 1\n\n### File changes\n- "
        + row["source"]
        + " (+0/-0)\n"
    )
    context_path = tmp_path / "verifier-context.md"
    context_path.write_text(context)
    diff_path = tmp_path / "verifier-pr-diff.patch"
    diff_path.write_bytes(patch)
    calls = []

    class Client:
        def invoke(self, prompt, **kwargs):
            calls.append(prompt)
            return SimpleNamespace(
                content=json.dumps({"verdict": "PASS", "summary": "Synthetic unit-only review."})
            )

    client = with_capacity(Client())
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda *a, **k: [])
    monkeypatch.setattr(
        pr_verifier.sys,
        "argv",
        [
            "pr_verifier.py",
            "--context-file",
            str(context_path),
            "--diff-file",
            str(diff_path),
            "--json",
        ],
    )
    pr_verifier.main()
    result = json.loads(capsys.readouterr().out)
    if failure:
        assert result["verdict"] != "PASS"
        assert calls == []
        assert client.root_client.responses.input_tokens.count.call_count == 0
    else:
        assert result["verdict"] == "PASS", json.dumps(result, indent=2)
        assert len(calls) == 1
        assert client.root_client.responses.input_tokens.count.call_count == 1
        assert "exact π proof" in calls[0] and criterion in calls[0]
        assert result["input_coverage"]["files_complete"] == 1


def test_existing_chunks_include_whole_asset_views_without_fabricating_git_patch(
    tmp_path, monkeypatch
):
    from tests.scripts.conftest import synthetic_verifier_capacity_contract
    from tests.scripts.test_pr_verifier_file_chunks import Client

    synthetic_verifier_capacity_contract.__wrapped__(monkeypatch)
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "1000")
    first, coverage, _ = asset(
        tmp_path, name="docs/verification/a.log.gz", text="first proof\n" * 220
    )
    second, other, _ = asset(
        tmp_path, name="docs/verification/b.log.gz", text="second proof\n" * 220
    )
    coverage["gzip_asset_sources"] += other["gzip_asset_sources"]
    coverage["changed_code_sources"] += other["changed_code_sources"]
    coverage["acceptance_source_discovery"] = {"required": False, "status": "included"}
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(first + second),
    }
    context = IDENTITY + (
        "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\nNo failure.\n\n## Plan sources (scope, tasks, acceptance)\n#### Acceptance criteria\n- Review the retained proof.\n"
    )
    client = Client()
    result = pr_verifier._evaluate_chunked(
        client, context, (first + second).decode(), "openai", None
    )
    assert result is not None
    assert result.files_not_reviewed == [], result.model_dump()
    assert result.input_coverage["files_complete"] == 2
    assert len(client.prompts) >= 3
    assert any("first proof\n" * 220 in prompt for prompt in client.prompts)
    assert any("second proof\n" * 220 in prompt for prompt in client.prompts)
    assert any(first.decode().strip() in prompt for prompt in client.prompts)
    assert any(second.decode().strip() in prompt for prompt in client.prompts)


@pytest.mark.parametrize("missing", [False, True])
def test_expanded_compare_existing_semantic_capture_and_reassembly(tmp_path, monkeypatch, missing):
    from tools.verifier_semantic_rules import prepare_residual_all_input

    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("PR_HEAD_SHA", "b" * 40)
    patch, coverage, row = asset(tmp_path)
    coverage["acceptance_source_discovery"] = {"required": False, "status": "included"}
    coverage["full_diff_artifact"] = {
        "source": "verifier-pr-diff.patch",
        "status": "included",
        "chars": len(patch.decode()),
    }
    context = (
        IDENTITY
        + "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\nNo failure.\n\n## Plan sources (scope, tasks, acceptance)\n#### Acceptance criteria\n- Preserve the complete original π request.\n"
    )
    if missing:
        (tmp_path / (row["raw_sha256"] + ".gz")).unlink()
    capture = pr_verifier._semantic_capture(context, patch.decode())
    if missing:
        assert not capture["resource_admitted"]
        assert any("gzip_asset" in gap for gap in capture["gaps"])
        return
    assert capture["resource_admitted"], capture["gaps"]
    raw = pr_verifier._semantic_raw_inputs(context, patch.decode())
    assert len(raw) == 3 and raw["diff"] == patch and raw["context"] == context.encode()
    key = "gzip_asset:" + hashlib.sha256(row["source"].encode()).hexdigest()
    assert row["input_id"] == key
    assert raw[key] == b"exact \xcf\x80 proof\r\n"
    prepared = prepare_residual_all_input(capture, raw)
    assert len(prepared["prompts"]) == 1
    request = next(iter(prepared["prompts"].values()))
    assert "exact π proof\r\n" in request["bytes"].decode("utf-8")
    assert "Preserve the complete original π request." in request["bytes"].decode("utf-8")
    assert patch.decode() in request["bytes"].decode("utf-8")
    assert set(prepared["plan"]["packages"][0]["raw_inputs"]) == set(raw)


@pytest.mark.parametrize(
    "field,value", [("repository", "evil/foreign"), ("evaluated_sha", "c" * 40)]
)
def test_row_and_binding_cannot_override_outer_target(tmp_path, monkeypatch, field, value):
    monkeypatch.setenv("VERIFIER_EVIDENCE_CAPTURE_DIR", str(tmp_path))
    patch, coverage, row = asset(tmp_path)
    row[field] = value
    coverage["gzip_asset_binding"][field] = value
    context = (
        IDENTITY
        + "## Context source coverage\n\n```json\n"
        + json.dumps(coverage)
        + "\n```\n\n## CI Information\n"
    )
    manifest = build_capture_obligation_manifest(context, full_diff_bytes=patch)
    assert not manifest["sufficient"]
    assert any("outer_target_identity_mismatch" in gap for gap in manifest["gaps"])
    assert (
        pr_verifier.build_prompt_inputs(context, patch.decode(), lossless=True)
        .coverage.files[0]
        .status
        == "omitted"
    )
