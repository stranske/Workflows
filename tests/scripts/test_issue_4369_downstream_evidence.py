"""Replay the bounded delivery observation without promoting it to acceptance."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from scripts.sync_manifest_compiler import compile_manifest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4369/runtime-4548/downstream-observation.json"
MAINT68 = ".github/workflows/maint-68-sync-consumer-repos.yml"
MAINT71 = ".github/workflows/maint-71-merge-sync-prs.yml"
DISCUSSION = "4434491702"


@pytest.fixture(
    scope="module", params=[EVIDENCE, EVIDENCE.with_stem("downstream-observation-complete")]
)
def receipt(request: pytest.FixtureRequest) -> dict:
    return json.loads(request.param.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def complete_receipt() -> dict:
    return json.loads(EVIDENCE.with_stem("downstream-observation-complete").read_text())


@pytest.fixture(scope="module")
def refreshed_receipt() -> dict:
    path = ROOT / "docs/evidence/issue-4369/runtime-4550/downstream-refresh.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def followup_receipt() -> dict:
    path = ROOT / "docs/evidence/issue-4369/runtime-4550/downstream-followup.json"
    return json.loads(path.read_text(encoding="utf-8"))


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() is not None
    return parsed


def runs(receipt: dict) -> list[dict]:
    return [run for page in receipt["collection"]["run_inventories"] for run in page["runs"]]


def test_inventory_preserves_bounded_event_collections(receipt: dict) -> None:
    inventories = receipt["collection"]["run_inventories"]
    events = {"schedule", "workflow_dispatch"}
    if receipt["schema"] == "issue-4369/downstream-observation/v2":
        events.add("repository_dispatch")
    assert {page["event"] for page in inventories} == events
    assert len(inventories) == len(events)
    for page in inventories:
        query = parse_qs(urlparse(page["url"]).query)
        assert query == {
            "event": [page["event"]],
            "per_page": ["100"],
            "created": [f'{page["start"]}..{page["end"]}'],
        }
        # An unfiltered single page is complete only when it contains the total.
        # Keeping interleaved workflows prevents cherry-picking a historical run.
        assert len(page["runs"]) == page["total_count"] < 100
        assert utc(page["end"]) < utc(receipt["observed_at"])
        assert utc(page["start"]) <= utc(receipt["source_pr"]["merged_at"])
        for run in page["runs"]:
            assert run["event"] == page["event"]
            assert utc(page["start"]) <= utc(run["created_at"]) <= utc(page["end"])
    inventory = runs(receipt)
    assert len({run["id"] for run in inventory}) == len(inventory)
    assert any(run["path"] not in {MAINT68, MAINT71} for run in inventory)


def test_latest_producer_is_not_a_regeneration_of_the_merged_fix(receipt: dict) -> None:
    producers = [run for run in runs(receipt) if run["path"] == MAINT68]
    latest = max(producers, key=lambda run: utc(run["created_at"]))
    assert latest == receipt["maint68"]["run"]
    source = receipt["source_pr"]
    assert source["merged"] is True
    assert source["merge_commit_sha"] == "9acdde6d5f0731bf968a6766d83f2b47db8375a3"
    assert latest["head_sha"] == receipt["maint68"]["source_sha"]
    assert latest["head_sha"] != source["merge_commit_sha"]
    assert utc(latest["created_at"]) < utc(source["merged_at"])
    # Completion after the source merge does not change a producer's frozen SHA.
    assert utc(source["merged_at"]) < utc(latest["updated_at"])


def test_successful_prepare_did_not_execute_consumer_delivery(receipt: dict) -> None:
    producer = receipt["maint68"]
    assert producer["run"]["conclusion"] == "success"
    jobs = producer["jobs"]
    assert all(job["run_id"] == producer["run"]["id"] for job in jobs)
    prepare = next(job for job in jobs if job["id"] == producer["prepare_job_id"])
    assert prepare["conclusion"] == "success"
    delivery = [job for job in jobs if job["name"].startswith("Sync ")]
    assert len(delivery) == 1
    assert delivery[0]["conclusion"] == "skipped"
    excerpts = "\n".join(producer["log_excerpts"])
    assert f'SOURCE_COMMIT: {producer["source_sha"]}' in excerpts
    assert f'Compiled 280 copy entries and 17 removals as {producer["plan_id"]}' in excerpts


def test_immediately_following_janitor_has_no_consumer_disposition(receipt: dict) -> None:
    producer = receipt["maint68"]["run"]
    following = receipt["following_maint71"]
    candidates = [
        run
        for run in runs(receipt)
        if run["path"] == MAINT71 and utc(run["created_at"]) > utc(producer["updated_at"])
    ]
    assert len(candidates) == 3
    assert min(candidates, key=lambda run: utc(run["created_at"])) == following["run"]
    assert following["run"]["id"] == 42451203202
    assert following["run"]["head_sha"] == receipt["source_pr"]["merge_commit_sha"]
    assert following["consumer_status"] == "no_prs"
    excerpts = "\n".join(following["log_excerpts"])
    assert '"owner": "stranske"' in excerpts
    assert '"repo": "Portable-Alpha-Extension-Model"' in excerpts
    assert '"status": "no_prs"' in excerpts
    # This has no consumer head or finding inventory to bind to the new payload.
    assert "review_finding_disposition" not in following


def test_retained_payload_bytes_prove_the_consumer_has_the_older_implementation(
    receipt: dict,
) -> None:
    source, consumer = (receipt["payloads"][key] for key in ("source", "consumer"))
    assert source["ref"] == receipt["source_pr"]["merge_commit_sha"]
    assert consumer["ref"] == receipt["consumer_pr"]["head_sha"]
    for payload in (source, consumer):
        content = payload["content"].encode("utf-8")
        git_object = f"blob {len(content)}\0".encode("ascii") + content
        assert hashlib.sha1(git_object).hexdigest() == payload["sha"]
        assert 'os.environ.get("CLAUDE_CONFIG_DIR"' in payload["content"]
    assert source["sha"] != consumer["sha"]
    normalization = "Path(config_dir).expanduser().resolve()"
    assert normalization in source["content"]
    assert normalization not in consumer["content"]
    assert utc(receipt["consumer_pr"]["merged_at"]) < utc(receipt["source_pr"]["merged_at"])


def test_worker_resolution_predates_final_source_delivery(receipt: dict) -> None:
    thread = receipt["thread"]
    assert thread["id"] == "PRRT_kwDOO15QxM6yXhfS"
    assert thread["is_resolved"] is thread["is_outdated"] is True
    original, disposition = thread["comments"]
    assert str(original["database_id"]) == DISCUSSION
    assert disposition["database_id"] == 4505043101
    assert disposition["author"] != original["author"]
    assert receipt["consumer_pr"]["head_sha"] in disposition["body"]
    assert utc(disposition["created_at"]) < utc(receipt["source_pr"]["merged_at"])
    assert receipt["consumer_pr"]["merged"] is True
    assert receipt["consumer_pr"]["draft"] is False


def test_complete_comment_observation_has_no_later_scoped_sync_core_recurrence(
    receipt: dict,
) -> None:
    comments = receipt["issue_comments"]
    assert len(comments) == receipt["collection"]["comments"]["returned"]
    assert len({comment["id"] for comment in comments}) == len(comments)
    sync = [c for c in comments if c["body"].startswith("<!-- sync-core/v1 handoff ")]
    scoped = [c for c in sync if f"#discussion_r{DISCUSSION}" in c["body"]]
    assert max(scoped, key=lambda comment: comment["id"])["id"] == 6649911684
    assert max(sync, key=lambda comment: comment["id"])["id"] == 6650145104
    for comment in sync:
        # The connector omits REST creation times. Use the explicit handoff round,
        # not a fabricated timestamp, and preserve every comment body for replay.
        round_stamp = re.search(r"\(round (\d{8}T\d{6}Z)\)", comment["body"])
        assert round_stamp is not None
        round_time = datetime.strptime(round_stamp[1], "%Y%m%dT%H%M%SZ").replace(
            tzinfo=utc(receipt["observed_at"]).tzinfo
        )
        assert round_time < utc(receipt["source_pr"]["merged_at"])
    assert receipt["final_delivery_acceptance"] is False
    assert len(receipt["pending_reasons"]) == 3


def test_complete_inventory_covers_all_top_level_workflow_triggers(complete_receipt: dict) -> None:
    events = set()
    for path in (MAINT68, MAINT71):
        workflow = yaml.load((ROOT / path).read_text(), Loader=yaml.BaseLoader)
        # workflow_call executes inside a caller's run; it has no separate
        # top-level run inventory. Include all other authored entry points.
        events.update(set(workflow["on"]) - {"workflow_call"})
    inventories = complete_receipt["collection"]["run_inventories"]
    assert {page["event"] for page in inventories} == events
    assert len({(page["start"], page["end"]) for page in inventories}) == 1
    # The newly collected trigger contains a real Maint 71 run. Omitting it
    # could otherwise make the immediate-following-run selection incomplete.
    dispatch = next(page for page in inventories if page["event"] == "repository_dispatch")
    assert any(run["path"] == MAINT71 for run in dispatch["runs"])


def test_default_branch_still_contains_the_pre_final_payload(complete_receipt: dict) -> None:
    main = complete_receipt["consumer_default_branch"]
    consumer = complete_receipt["consumer_pr"]
    payload = complete_receipt["payloads"]["consumer"]
    assert main["head_sha"] == consumer["merge_commit_sha"]
    assert main["retained_content"] == "payloads.consumer.content"
    assert main["sha"] == payload["sha"]
    assert main["path"] == payload["path"]
    assert parse_qs(urlparse(main["payload_url"]).query) == {"ref": [main["head_sha"]]}
    assert main["sha"] != complete_receipt["payloads"]["source"]["sha"]


def test_rest_comments_bound_nonrecurrence_to_actual_creation_times(complete_receipt: dict) -> None:
    collection = complete_receipt["collection"]["comments"]
    comments = complete_receipt["issue_comments"]
    assert parse_qs(urlparse(collection["url"]).query) == {"per_page": ["100"]}
    assert collection["page"] == 1
    assert len(comments) == collection["returned"] < collection["per_page"]
    for comment in comments:
        assert utc(comment["created_at"]) <= utc(comment["updated_at"])
        assert utc(comment["updated_at"]) < utc(complete_receipt["observed_at"])
    sync = [comment for comment in comments if comment["body"].startswith("<!-- sync-core/v1 ")]
    scoped = [comment for comment in sync if f"#discussion_r{DISCUSSION}" in comment["body"]]
    assert max(scoped, key=lambda comment: utc(comment["created_at"]))["id"] == 6649911684
    assert all(
        utc(comment["created_at"]) < utc(complete_receipt["source_pr"]["merged_at"])
        for comment in sync
    )


def test_refreshed_inventory_covers_every_page_and_trigger(refreshed_receipt: dict) -> None:
    inventory = refreshed_receipt["collection"]["run_inventory"]
    pages = inventory["pages"]
    total = pages[0]["total_count"]
    capacity = inventory["per_page"]
    assert len(pages) == (total + capacity - 1) // capacity
    observed = utc(refreshed_receipt["observed_at_utc"])
    start, end = (utc(inventory[key]) for key in ("start", "end"))
    assert start < end < observed
    collected = []
    for number, page in enumerate(pages, start=1):
        assert page["page"] == number
        assert page["total_count"] == total
        url = urlparse(page["url"])
        assert url.path == "/repos/stranske/Workflows/actions/runs"
        # No event filter: a newly introduced trigger cannot hide a producer or
        # the immediately following Maint 71 run from this observation.
        assert parse_qs(url.query) == {
            "per_page": [str(capacity)],
            "page": [str(number)],
            "created": [f'{inventory["start"]}..{inventory["end"]}'],
        }
        assert len(page["runs"]) == min(capacity, total - (number - 1) * capacity)
        assert all(start <= utc(run["created_at"]) <= end for run in page["runs"])
        collected.extend(page["runs"])
    assert len({run["id"] for run in collected}) == total
    assert {"schedule", "workflow_dispatch", "repository_dispatch"} <= {
        run["event"] for run in collected
    }
    assert not any(run["path"] in {MAINT68, MAINT71} for run in collected)


def test_refreshed_payload_binding_keeps_final_delivery_pending(refreshed_receipt: dict) -> None:
    payloads = refreshed_receipt["payloads"]
    source, consumer = (payloads[key] for key in ("source", "consumer"))
    assert source["ref"] == "9acdde6d5f0731bf968a6766d83f2b47db8375a3"
    assert source["path"] == "templates/consumer-repo/tools/subscription_llm.py"
    assert consumer["path"] == "tools/subscription_llm.py"
    branch = refreshed_receipt["consumer_default_branch"]
    assert consumer["ref"] == branch["sha"]
    assert branch["name"] == "main"
    assert urlparse(branch["url"]).path == (f'/repos/{consumer["repository"]}/branches/main')
    for key, payload in payloads.items():
        repository = refreshed_receipt["consumer_repository" if key == "consumer" else "repository"]
        assert payload["repository"] == repository
        assert payload["url"] == (
            f'https://github.com/{repository}/blob/{payload["ref"]}/{payload["path"]}'
        )
        content = payload["content"].encode("utf-8")
        git_object = f"blob {len(content)}\0".encode("ascii") + content
        assert hashlib.sha1(git_object).hexdigest() == payload["sha"]
    # A resolved historical finding and a merged older candidate are insufficient
    # when the exact default-branch bytes still differ from the frozen source.
    assert source["sha"] != consumer["sha"]
    assert "Path(config_dir).expanduser().resolve()" in source["content"]
    assert "Path(config_dir).expanduser().resolve()" not in consumer["content"]
    assert refreshed_receipt["final_delivery_acceptance"] is False


@pytest.mark.parametrize("payload_key", ["source", "consumer"])
@pytest.mark.parametrize("field", ["repository", "url"])
def test_refreshed_binding_rejects_substituted_metadata(
    refreshed_receipt: dict, payload_key: str, field: str
) -> None:
    mutated = deepcopy(refreshed_receipt)
    payload = mutated["payloads"][payload_key]
    if field == "repository":
        payload[field] = "stranske/unrelated"
        # Keep related metadata consistent so receipt ownership is decisive.
        payload["url"] = (
            f'https://github.com/{payload[field]}/blob/{payload["ref"]}/{payload["path"]}'
        )
        if payload_key == "consumer":
            mutated["consumer_default_branch"][
                "url"
            ] = f"https://api.github.com/repos/{payload[field]}/branches/main"
    else:
        payload[field] += "-substituted"
    with pytest.raises(AssertionError):
        test_refreshed_payload_binding_keeps_final_delivery_pending(mutated)


def test_failed_dispatch_does_not_fabricate_a_following_lifecycle(refreshed_receipt: dict) -> None:
    dispatch = refreshed_receipt["dispatch"]
    assert dispatch["workflow"] == MAINT68
    assert dispatch["ref"] == "main"
    inputs = dispatch["inputs"]
    assert inputs["repos"] == refreshed_receipt["consumer_repository"]
    assert inputs["scope_head_sha"] == refreshed_receipt["payloads"]["source"]["ref"]
    assert inputs["scope_base_sha"] == "7e377b7ad8cc06e506393218bc7459ba47757f01"
    assert inputs["delivery_scope"] == "source-delta"
    assert inputs["phase"] == "canary"
    assert inputs["cleanup_branches"] == "false"
    canaries = json.loads((ROOT / "config/consumer_sync_canaries.json").read_text())
    assert inputs["repos"] in {entry["repo"] for entry in canaries["canaries"]}
    assert dispatch["exit_code"] != 0
    assert "error connecting to api.github.com" in dispatch["output"]
    assert dispatch["maint71_dispatched"] is False
    assert "run_id" not in dispatch


def test_refreshed_comment_observation_and_historical_thread_disposition(
    refreshed_receipt: dict,
) -> None:
    collection = refreshed_receipt["collection"]["comments"]
    comments = refreshed_receipt["issue_comments"]
    assert parse_qs(urlparse(collection["url"]).query) == {
        "per_page": [str(collection["per_page"])],
        "page": ["1"],
    }
    assert urlparse(collection["url"]).path == "/repos/stranske/Workflows/issues/4369/comments"
    assert collection["page"] == 1
    # The final short page proves completeness, rather than relying on a fixed
    # historical comment count or treating one full page as the entire history.
    assert len(comments) == collection["returned"] < collection["per_page"]
    assert len({comment["id"] for comment in comments}) == len(comments)
    through = utc(collection["observed_through_utc"])
    assert through <= utc(refreshed_receipt["observed_at_utc"])
    assert all(utc(comment["updated_at"]) <= through for comment in comments)
    scoped = [
        comment
        for comment in comments
        if comment["body"].startswith("<!-- sync-core/v1 ")
        and f"#discussion_r{DISCUSSION}" in comment["body"]
    ]
    last = max(scoped, key=lambda comment: utc(comment["created_at"]))
    assert last["id"] == 6649911684
    assert "round 20261105T044440Z" in last["body"]
    assert utc(last["created_at"]) < utc(refreshed_receipt["collection"]["run_inventory"]["start"])
    thread = refreshed_receipt["thread"]
    original, disposition = thread["comments"]
    assert str(original["database_id"]) == DISCUSSION
    assert thread["is_resolved"] is thread["is_outdated"] is True
    assert disposition["database_id"] == 4505043101
    assert "9c85282d05359ddc468d0881ec6b09269ac592a2" in disposition["body"]
    assert utc(disposition["created_at"]) < utc(
        refreshed_receipt["collection"]["run_inventory"]["start"]
    )


def test_followup_binds_the_frozen_manifest_to_the_root_and_template_payloads(
    followup_receipt: dict, tmp_path: Path
) -> None:
    payloads = followup_receipt["payloads"]
    source, template, manifest, consumer = (
        payloads[key] for key in ("source", "template", "manifest", "consumer")
    )
    frozen = followup_receipt["dispatch"]["inputs"]["scope_head_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", frozen)
    for key, payload in payloads.items():
        content = payload["content"].encode("utf-8")
        git_object = f"blob {len(content)}\0".encode("ascii") + content
        assert hashlib.sha1(git_object).hexdigest() == payload["sha"]
        repository = followup_receipt["consumer_repository" if key == "consumer" else "repository"]
        assert payload["repository"] == repository
        ref = followup_receipt["consumer_default_branch"]["sha"] if key == "consumer" else frozen
        assert payload["ref"] == ref
        assert payload["url"] == f'https://github.com/{repository}/blob/{ref}/{payload["path"]}'

    assert template["path"] == f'templates/consumer-repo/{source["path"]}'
    assert source["content"] == template["content"]
    assert source["sha"] == template["sha"] != consumer["sha"]
    # Compile the selected entry from the retained immutable manifest against
    # its retained bytes. Historical evidence must not depend on today's files.
    raw_manifest = yaml.safe_load(manifest["content"])
    selected = [entry for entry in raw_manifest["scripts"] if entry["source"] == source["path"]]
    assert len(selected) == 1
    for payload in (source, template):
        path = tmp_path / payload["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload["content"].encode("utf-8"))
    manifest_path = tmp_path / manifest["path"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump({"version": raw_manifest["version"], "scripts": selected}),
        encoding="utf-8",
    )
    (entry,) = compile_manifest(manifest_path).all_entries()
    assert entry.source_tree == "root"
    assert entry.resolved_source == source["path"]
    assert entry.target == consumer["path"] == "tools/subscription_llm.py"
    assert entry.delivery == "copy"
    assert entry.template_sync == "exact"
    assert (
        entry.content_sha256 == "sha256:" + hashlib.sha256(source["content"].encode()).hexdigest()
    )
    repo = followup_receipt["consumer_repository"]
    assert not entry.include_repos or repo in entry.include_repos
    assert repo not in {rule.repo for rule in entry.skip_repos}


def test_followup_inventory_does_not_confuse_other_maint71_workflows_with_delivery(
    followup_receipt: dict,
) -> None:
    inventory = followup_receipt["collection"]["run_inventory"]
    (page,) = inventory["pages"]
    assert page["page"] == 1
    assert len(page["runs"]) == page["total_count"] < inventory["per_page"]
    assert parse_qs(urlparse(page["url"]).query) == {
        "per_page": [str(inventory["per_page"])],
        "page": ["1"],
        "created": [f'{inventory["start"]}..{inventory["end"]}'],
    }
    assert len({run["id"] for run in page["runs"]}) == page["total_count"]
    assert (
        utc(inventory["start"]) < utc(inventory["end"]) < utc(followup_receipt["observed_at_utc"])
    )
    assert all(
        utc(inventory["start"]) <= utc(run["created_at"]) <= utc(inventory["end"])
        for run in page["runs"]
    )
    assert not any(run["path"] in {MAINT68, MAINT71} for run in page["runs"])
    assert any(
        run["path"] == ".github/workflows/maint-71-auto-fix-integration.yml" for run in page["runs"]
    )
    dispatch = followup_receipt["dispatch"]
    assert dispatch["workflow"] == MAINT68
    assert dispatch["inputs"]["repos"] == followup_receipt["consumer_repository"]
    assert dispatch["exit_code"] != 0
    assert "error connecting to api.github.com" in dispatch["output"]
    assert dispatch["maint71_dispatched"] is False
    assert "run_id" not in dispatch
    assert followup_receipt["final_delivery_acceptance"] is False


def test_followup_rest_comment_pages_agree_with_the_all_pages_connector(
    followup_receipt: dict,
) -> None:
    collection = followup_receipt["collection"]["comments"]
    (page,) = collection["pages"]
    assert page["page"] == 1
    assert parse_qs(urlparse(page["url"]).query) == {
        "per_page": [str(collection["per_page"])],
        "page": ["1"],
    }
    assert urlparse(page["url"]).path == "/repos/stranske/Workflows/issues/4369/comments"
    comments = page["comments"]
    assert len(comments) < collection["per_page"]
    ids = [comment["id"] for comment in comments]
    connector = collection["all_pages_connector"]
    assert ids == connector["ids"]
    assert len(set(ids)) == connector["returned"] == len(comments)
    through = utc(collection["observed_through_utc"])
    assert through <= utc(followup_receipt["observed_at_utc"])
    assert all(
        utc(comment["created_at"]) <= utc(comment["updated_at"]) <= through for comment in comments
    )
    scoped = [
        comment
        for comment in comments
        if comment["body"].startswith("<!-- sync-core/v1 ")
        and re.search(rf"#discussion_r{DISCUSSION}(?!\d)", comment["body"])
    ]
    last = max(scoped, key=lambda comment: utc(comment["created_at"]))
    assert last["id"] == 6649911684
    assert utc(last["created_at"]) < utc(followup_receipt["collection"]["run_inventory"]["start"])


def test_followup_thread_resolution_still_predates_the_final_payload_observation(
    followup_receipt: dict,
) -> None:
    thread = followup_receipt["thread"]
    assert thread["is_resolved"] is thread["is_outdated"] is True
    original, disposition = thread["comments"]
    assert str(original["database_id"]) == DISCUSSION
    assert disposition["database_id"] == 4505043101
    assert "9c85282d05359ddc468d0881ec6b09269ac592a2" in disposition["body"]
    assert utc(disposition["created_at"]) < utc(
        followup_receipt["collection"]["run_inventory"]["start"]
    )
    assert "following_maint71" not in followup_receipt
    assert followup_receipt["final_delivery_acceptance"] is False
