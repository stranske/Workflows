"""Check global resource admission without confusing ZIP listings with proof."""

import copy
import hashlib
import json
import sys
import zipfile

import pytest
from tools import verifier_proof_resource_plan as planner


@pytest.fixture
def packet(tmp_path):
    path = tmp_path / "proof.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("red.txt", b"failure")
        archive.writestr("green.txt", b"pass")
    record = {
        "artifact_id": 1,
        "repository": "owner/repo",
        "run_id": 2,
        "head_sha": "a" * 40,
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "archive_bytes": path.stat().st_size,
    }
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "id": 1,
                "url": "https://api.github.com/repos/owner/repo/actions/artifacts/1",
                "workflow_run": {"id": 2, "head_sha": "a" * 40},
                "digest": f"sha256:{record['archive_sha256']}",
                "size_in_bytes": record["archive_bytes"],
            }
        )
    )
    record["metadata_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    return {"context": b"original incomplete capture"}, [record], {1: path}, {1: metadata}


def test_no_member_decompression_or_provider_execution(packet, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline admission must not extract member content")

    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden)
    plan = planner.build_resource_plan(*packet)
    assert plan["required_extraction_bytes"] == 11
    assert plan["provider_calls"] == plan["extracted_bytes"] == plan["rendered_bytes"] == 0
    assert not plan["admitted"] and not plan["semantic_packages"]
    assert plan["capture_reassembly_contract"]["gaps"]
    assert all(x["content_sha256"] is None for x in plan["member_occurrences"])


def test_counter_is_global_across_archives_without_deduplication(packet, monkeypatch):
    inputs, records, paths, metadata_paths = packet
    second = {**records[0], "artifact_id": 3}
    metadata = json.loads(metadata_paths[1].read_text())
    metadata.update(id=3, url="https://api.github.com/repos/owner/repo/actions/artifacts/3")
    second_metadata = metadata_paths[1].with_name("second-metadata.json")
    second_metadata.write_text(json.dumps(metadata))
    second["metadata_sha256"] = hashlib.sha256(second_metadata.read_bytes()).hexdigest()
    monkeypatch.setattr(planner, "TOTAL_EXTRACT_BYTES", 15)
    plan = planner.build_resource_plan(
        inputs, records + [second], {**paths, 3: paths[1]}, {**metadata_paths, 3: second_metadata}
    )
    assert plan["required_extraction_bytes"] == 22
    assert len(plan["member_occurrences"]) == 4
    assert len({x["id"] for x in plan["member_occurrences"]}) == 4
    assert "global-extraction-bound" in plan["blockers"]
    assert plan["extracted_bytes"] == plan["provider_calls"] == 0


@pytest.mark.parametrize("change", ["occurrence", "gap", "head", "range", "admission", "counter"])
def test_tampering_and_severed_global_bindings_fail_then_exact_restore_passes(packet, change):
    original = planner.build_resource_plan(*packet)
    plan = copy.deepcopy(original)
    if change == "occurrence":
        plan["member_occurrences"].pop()
    elif change == "gap":
        plan["capture_reassembly_contract"]["gaps"] = []
    elif change == "head":
        plan["archives"][0]["head_sha"] = "b" * 40
    elif change == "range":
        plan["capture_reassembly_contract"]["required_range_ids"] = []
    elif change == "admission":
        plan["admitted"] = True
    else:
        plan["required_extraction_bytes"] = 0
    with pytest.raises(ValueError, match="full frozen capture"):
        planner.validate_resource_plan(plan, *packet)
    planner.validate_resource_plan(original, *packet)


def test_omitted_archive_and_changed_raw_bytes_fail(packet):
    inputs, records, paths, metadata_paths = packet
    with pytest.raises(ValueError, match="exact expected inventory"):
        planner.build_resource_plan(inputs, records, {}, metadata_paths)
    paths[1].write_bytes(paths[1].read_bytes() + b"altered")
    with pytest.raises(ValueError, match="bytes differ"):
        planner.build_resource_plan(inputs, records, paths, metadata_paths)


def test_metadata_bound_and_duplicate_artifact_identity_fail(packet, monkeypatch):
    inputs, records, paths, metadata_paths = packet
    monkeypatch.setattr(planner, "MAX_MEMBERS", 1)
    with pytest.raises(ValueError, match="finite metadata bound"):
        planner.build_resource_plan(*packet)
    with pytest.raises(ValueError, match="duplicate"):
        planner.build_resource_plan(inputs, records * 2, paths, metadata_paths)


def test_wrong_head_and_rehashed_provenance_fail(packet):
    inputs, records, paths, metadata_paths = packet
    wrong = [{**records[0], "head_sha": "b" * 40}]
    with pytest.raises(ValueError, match="provenance"):
        planner.build_resource_plan(inputs, wrong, paths, metadata_paths)
    metadata = json.loads(metadata_paths[1].read_text())
    metadata["workflow_run"]["head_sha"] = "b" * 40
    metadata_paths[1].write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="metadata differs"):
        planner.build_resource_plan(*packet)


def test_cli_retains_full_packet_and_refuses_existing_output(packet, tmp_path, monkeypatch):
    inputs, records, paths, metadata_paths = packet
    context = tmp_path / "context.md"
    context.write_bytes(inputs["context"])
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "expected_archives": records,
                "archive_paths": {k: str(v) for k, v in paths.items()},
                "metadata_paths": {k: str(v) for k, v in metadata_paths.items()},
            }
        )
    )
    output = tmp_path / "plan.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "planner",
            "--context",
            str(context),
            "--inventory",
            str(inventory),
            "--output",
            str(output),
        ],
    )
    assert planner.main() == 0
    original = output.read_bytes()
    planner.validate_resource_plan(json.loads(original), *packet)
    with pytest.raises(FileExistsError):
        planner.main()
    assert output.read_bytes() == original
    assert context.read_bytes() == inputs["context"]
