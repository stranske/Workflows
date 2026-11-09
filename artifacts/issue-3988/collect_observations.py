"""Read-only, paginated GitHub evidence collector for issue #4458.

Run this script with /opt/anaconda3/bin/python3 from the repository root.
Only queries explicit repositories from the merge-commit consumer registry plus
Workflows. Does not use search, current labels for eligibility, or branch names
to infer routing. No GitHub mutations.
"""

import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

MERGE = "3e7f75d3750e54a1453cf9ea0ce4ed048bf24288"
START = "2026-11-07T02:51:20Z"
END = "2026-11-09T02:51:20Z"
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent


def api(endpoint):
    errors = []
    for _ in range(2):
        result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=45)
        if result.returncode == 0:
            return json.loads(result.stdout)
        errors.append(result.stderr.strip())
    raise RuntimeError({"endpoint": endpoint, "errors": errors})


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def collect_repo(repo):
    coverage = {"repository": repo, "pull_pages": [], "complete": False}
    observations = []
    try:
        for page in range(1, 101):
            endpoint = (
                f"repos/{repo}/pulls?state=all&sort=created&direction=desc"
                f"&per_page=100&page={page}"
            )
            rows = api(endpoint)
            coverage["pull_pages"].append(
                {
                    "endpoint": endpoint,
                    "count": len(rows),
                    "newest_created_at": rows[0]["created_at"] if rows else None,
                    "oldest_created_at": rows[-1]["created_at"] if rows else None,
                }
            )
            for row in rows:
                if not START <= row["created_at"] < END:
                    continue
                record = {
                    "repository": repo,
                    "number": row["number"],
                    "url": row["html_url"],
                    "created_at": row["created_at"],
                    "timeline_pages": [],
                    "label_events": [],
                    "history_complete": False,
                }
                observations.append(record)
                try:
                    for event_page in range(1, 101):
                        timeline_endpoint = (
                            f"repos/{repo}/issues/{row['number']}/timeline"
                            f"?per_page=100&page={event_page}"
                        )
                        events = api(timeline_endpoint)
                        record["timeline_pages"].append(
                            {"endpoint": timeline_endpoint, "count": len(events)}
                        )
                        for event in events:
                            if event.get("event") in ("labeled", "unlabeled"):
                                record["label_events"].append(
                                    {
                                        "id": event.get("id"),
                                        "url": event.get("url"),
                                        "event": event["event"],
                                        "created_at": event["created_at"],
                                        "label": event["label"]["name"],
                                    }
                                )
                        if len(events) < 100:
                            record["history_complete"] = True
                            break
                    else:
                        record["history_error"] = "timeline page bound exceeded"
                except Exception as error:
                    record["history_error"] = str(error)
            if len(rows) < 100 or rows[-1]["created_at"] < START:
                coverage["complete"] = True
                break
        else:
            coverage["error"] = "pull page bound exceeded"
    except Exception as error:
        coverage["error"] = str(error)
    coverage["window_pr_count"] = len(observations)
    coverage["histories_complete"] = all(r["history_complete"] for r in observations)
    save(repo.split("/")[1] + "-histories.json", observations)
    print(
        repo,
        coverage["window_pr_count"],
        coverage["complete"],
        coverage["histories_complete"],
        flush=True,
    )
    return coverage, observations


STATUS_LABELS = frozenset({"agent:retry", "agent:rate-limited", "agent:needs-attention"})


def classify_record(record, end=END):
    """Classify saved history without I/O; removals do not erase earlier routing."""
    events = sorted(record["label_events"], key=lambda e: (e["created_at"], e["id"]))
    keepalive = [
        e
        for e in events
        if e["event"] == "labeled" and e["label"] == "agents:keepalive" and e["created_at"] < end
    ]
    routing = [
        e
        for e in events
        if e["event"] == "labeled"
        and e["label"].startswith("agent:")
        and e["created_at"] < end
        and e["label"] not in STATUS_LABELS
    ]
    item = {k: record[k] for k in ("repository", "number", "url", "created_at")}
    if not record["history_complete"]:
        return "unknown", {**item, "reason": record.get("history_error", "incomplete history")}
    elif not keepalive:
        return "excluded", {**item, "reason": "no agents:keepalive label event before window end"}
    else:
        first = routing[0] if routing else None
        # Equal timestamps do not prove ordering between distinct routing agents.
        tied = sorted(
            {e["label"] for e in routing if first and e["created_at"] == first["created_at"]}
        )
        concrete = [e for e in routing if e["label"] != "agent:auto"]
        item.update(
            {
                "first_keepalive_event": keepalive[0],
                "first_routing_event": first,
                "tied_first_labels": tied,
                "routing_status": (
                    "absent" if not first else "ambiguous" if len(tied) > 1 else "observed"
                ),
                "non_codex": bool(tied) and all(label != "agent:codex" for label in tied),
                "first_concrete_routing_event": concrete[0] if concrete else None,
                "concrete_non_codex": bool(concrete) and concrete[0]["label"] != "agent:codex",
            }
        )
        return "eligible", item


def main():
    workflow = subprocess.check_output(
        ["git", "show", f"{MERGE}:.github/workflows/maint-68-sync-consumer-repos.yml"],
        cwd=ROOT,
        text=True,
    )
    block = workflow.split("  REGISTERED_CONSUMER_REPOS: |\n", 1)[1].split("\n\n", 1)[0]
    # Exclusions are applied before making any API request or writing inventories.
    repos = [r.strip() for r in block.splitlines() if r.strip()]
    repos = [r for r in repos if r.casefold() != "stranske/" + "collab-admin"]
    repos = ["stranske/Workflows", *repos]
    coverage, observations = [], []
    if "--from-saved" in sys.argv:
        previous = json.loads((OUT / "routing-observations.json").read_text(encoding="utf-8"))
        coverage = previous["repository_coverage"]
        for repo in repos:
            observations.extend(
                json.loads(
                    (OUT / (repo.split("/")[1] + "-histories.json")).read_text(encoding="utf-8")
                )
            )
        collected_at = previous["collected_at"]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for c, rows in pool.map(collect_repo, repos):
                coverage.append(c)
                observations.extend(rows)
        collected_at = dt.datetime.now(dt.timezone.utc).isoformat()
    eligible, exclusions, unknown = [], [], []
    buckets = {"eligible": eligible, "excluded": exclusions, "unknown": unknown}
    for record in observations:
        classification, item = classify_record(record)
        buckets[classification].append(item)
    numerator = sum(r.get("non_codex", False) for r in eligible)
    denominator = len(eligible)
    ambiguous = sum(
        "agent:codex" in r["tied_first_labels"]
        and any(label != "agent:codex" for label in r["tied_first_labels"])
        for r in eligible
    )
    complete = all(c["complete"] and c["histories_complete"] for c in coverage) and not unknown
    elapsed = dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(
        END.replace("Z", "+00:00")
    )
    share = numerator / denominator if denominator else None
    # Provider redistribution is a separate limitation; A4 specifies labels other than agent:codex.
    provider_numerator = sum(
        bool(r["tied_first_labels"])
        and all(label not in ("agent:auto", "agent:codex") for label in r["tied_first_labels"])
        for r in eligible
    )
    provider_ambiguous = sum(
        any(label not in ("agent:auto", "agent:codex") for label in r["tied_first_labels"])
        and any(label in ("agent:auto", "agent:codex") for label in r["tied_first_labels"])
        for r in eligible
    )
    provider_share = provider_numerator / denominator if denominator else None
    result = {
        "schema": "workflows.issue-4458-routing-observations/v1",
        "collected_at": collected_at,
        "merge_commit": MERGE,
        "window_start_inclusive": START,
        "window_end_exclusive": END,
        "window_elapsed": elapsed,
        "fleet_source": f"{MERGE}:.github/workflows/maint-68-sync-consumer-repos.yml REGISTERED_CONSUMER_REPOS plus source Workflows",
        "method": "Enumerate all PRs by creation time, including closed PRs; exhaust each in-window PR timeline. Eligible means keepalive-labeled before window end, even if later removed. Routing excludes known control/status labels (agent:retry, agent:rate-limited, agent:needs-attention). Literal first routing includes agent:auto, matching the named suite's routing-label contract. Complete histories without any routing label count in the denominator but not the numerator. Mixed same-second first labels produce conservative numerator bounds. Later delegation is never substituted for the first label. A separate provider metric excludes agent:auto. Histories are stored per repository. No search index or present-day-label filter.",
        "repository_coverage": coverage,
        "complete_coverage": complete,
        "eligible_keepalive_prs": eligible,
        "exclusions": exclusions,
        "unavailable_histories": unknown,
        "numerator": numerator,
        "denominator": denominator,
        "non_codex_share": share,
        "numerator_upper_bound": numerator + ambiguous,
        "share_upper_bound": (numerator + ambiguous) / denominator if denominator else None,
        "same_second_ambiguous_pr_count": ambiguous,
        "no_routing_label_count": sum(r["routing_status"] == "absent" for r in eligible),
        "concrete_provider_metric": {
            "numerator": sum(r["concrete_non_codex"] for r in eligible),
            "denominator": denominator,
            "share": (
                sum(r["concrete_non_codex"] for r in eligible) / denominator
                if denominator
                else None
            ),
            "no_concrete_routing_label_count": sum(
                r["first_concrete_routing_event"] is None for r in eligible
            ),
        },
        "threshold": 0.30,
        "literal_label_verdict": (
            "UNKNOWN"
            if not complete or not elapsed or not denominator
            else (
                "PASS"
                if share >= 0.30
                else "FAIL" if (numerator + ambiguous) / denominator < 0.30 else "UNKNOWN"
            )
        ),
        "first_label_provider_metric": {
            "definition": "First routing label identifies a non-Codex provider; agent:auto is not credited. Same-second mixed labels use conservative bounds.",
            "numerator": provider_numerator,
            "denominator": denominator,
            "share": provider_share,
            "numerator_upper_bound": provider_numerator + provider_ambiguous,
        },
        "acceptance_metric": {
            "definition": "First routing label is not agent:codex, as specified in issue #4458; includes agent:auto. Same-second mixed labels use conservative bounds.",
            "numerator": numerator,
            "denominator": denominator,
            "share": share,
            "numerator_upper_bound": numerator + ambiguous,
        },
        "verdict": (
            "UNKNOWN"
            if not complete or not elapsed or not denominator
            else (
                "PASS"
                if share >= 0.30
                else ("FAIL" if (numerator + ambiguous) / denominator < 0.30 else "UNKNOWN")
            )
        ),
        "limitations": [
            "Observed label history does not establish a particular chooser invocation, pool capacity at assignment, or causal attribution to PR #4505.",
            "agent:auto is a routing label in the named test contract, but does not identify a concrete non-Codex provider. A4 label-measure PASS does not establish provider redistribution or the separate A3 production-summary condition.",
        ],
    }
    save("routing-observations.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "numerator",
                    "denominator",
                    "non_codex_share",
                    "complete_coverage",
                    "acceptance_metric",
                    "verdict",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
