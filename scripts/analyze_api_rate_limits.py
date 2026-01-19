#!/usr/bin/env python3
"""Analyze GitHub API rate limits across multiple authentication methods and repositories.

This script provides detailed insights into API rate limit utilization to help identify
which processes are consuming API limits and how well the load is distributed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class RateLimitInfo:
    """Rate limit information for a specific resource."""

    limit: int
    remaining: int
    used: int
    reset_timestamp: int

    @property
    def utilization_pct(self) -> float:
        """Return utilization percentage."""
        if self.limit == 0:
            return 0.0
        return (self.used / self.limit) * 100

    @property
    def reset_time(self) -> str:
        """Return human-readable reset time."""
        try:
            dt = datetime.fromtimestamp(self.reset_timestamp, tz=UTC)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (OSError, ValueError):
            return "unknown"


@dataclass
class TokenRateLimits:
    """Rate limits for all resources under a single token."""

    source: str
    core: RateLimitInfo
    graphql: RateLimitInfo
    search: RateLimitInfo
    code_search: RateLimitInfo | None = None
    actions_runner: RateLimitInfo | None = None

    @classmethod
    def from_api_response(cls, source: str, data: dict[str, Any]) -> TokenRateLimits:
        """Create from GitHub API rate_limit response."""
        resources = data.get("resources", {})

        def extract(name: str) -> RateLimitInfo:
            r = resources.get(name, {})
            return RateLimitInfo(
                limit=r.get("limit", 0),
                remaining=r.get("remaining", 0),
                used=r.get("used", 0),
                reset_timestamp=r.get("reset", 0),
            )

        return cls(
            source=source,
            core=extract("core"),
            graphql=extract("graphql"),
            search=extract("search"),
            code_search=extract("code_search") if "code_search" in resources else None,
            actions_runner=(
                extract("actions_runner_registration")
                if "actions_runner_registration" in resources
                else None
            ),
        )


def get_rate_limits(token: str | None = None) -> dict[str, Any] | None:
    """Get rate limits using the GitHub CLI."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token

    try:
        result = subprocess.run(
            ["gh", "api", "rate_limit"],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to get rate limits: {e}", file=sys.stderr)
        return None


def get_workflow_runs(repo: str, token: str | None = None) -> dict[str, Any]:
    """Get recent workflow runs for a repository."""
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token

    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/runs",
                "-f",
                "per_page=100",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Warning: Failed to get workflow runs for {repo}: {e}", file=sys.stderr)
        return {"workflow_runs": [], "total_count": 0}


def _parse_github_timestamp(value: str) -> datetime | None:
    """Parse GitHub timestamp strings into timezone-aware datetimes."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_run_timestamp(run: dict[str, Any]) -> datetime | None:
    """Select the best available timestamp for a workflow run."""
    for key in ("created_at", "run_started_at", "updated_at"):
        value = run.get(key)
        if not value:
            continue
        parsed = _parse_github_timestamp(str(value))
        if parsed:
            return parsed
    return None


def summarize_workflow_activity(
    repos: list[str],
    *,
    token: str | None = None,
    hours: int = 1,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Summarize recent workflow activity for the requested repositories."""
    if not repos:
        return []

    window_start = (now or datetime.now(tz=UTC)) - timedelta(hours=hours)
    summaries: list[dict[str, Any]] = []

    for repo in repos:
        data = get_workflow_runs(repo, token=token)
        runs_raw = data.get("workflow_runs", [])
        runs = runs_raw if isinstance(runs_raw, list) else []
        recent_runs = []
        for run in runs:
            created_dt = _extract_run_timestamp(run)
            if created_dt and created_dt >= window_start:
                recent_runs.append(run)
        summaries.append(
            {
                "repo": repo,
                "window_hours": hours,
                "recent_runs": len(recent_runs),
                "total_runs": (
                    data.get("total_count")
                    if isinstance(data.get("total_count"), int)
                    else len(runs)
                ),
            }
        )

    return summaries


def analyze_rate_limits(tokens: dict[str, str | None]) -> list[TokenRateLimits]:
    """Analyze rate limits for multiple tokens."""
    results = []

    for name, token in tokens.items():
        data = get_rate_limits(token)
        if data:
            results.append(TokenRateLimits.from_api_response(name, data))

    return results


def print_utilization_table(limits: list[TokenRateLimits]) -> None:
    """Print a formatted utilization table."""
    print("\n" + "=" * 80)
    print("API RATE LIMIT UTILIZATION REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-" * 80)

    # Header
    print(f"{'Token':<25} {'Core API':<20} {'GraphQL':<20} {'Search':<15}")
    print(f"{'':<25} {'Used/Limit (%)':<20} {'Used/Limit (%)':<20} {'Used/Limit (%)':<15}")
    print("-" * 80)

    for trl in limits:
        core_str = f"{trl.core.used}/{trl.core.limit} ({trl.core.utilization_pct:.1f}%)"
        graphql_str = f"{trl.graphql.used}/{trl.graphql.limit} ({trl.graphql.utilization_pct:.1f}%)"
        search_str = f"{trl.search.used}/{trl.search.limit} ({trl.search.utilization_pct:.1f}%)"
        print(f"{trl.source:<25} {core_str:<20} {graphql_str:<20} {search_str:<15}")

    print("-" * 80)


def print_warnings(limits: list[TokenRateLimits]) -> list[str]:
    """Print warnings for high utilization and return list of warnings."""
    warnings = []
    print("\n⚠️  UTILIZATION WARNINGS")
    print("-" * 40)

    has_warnings = False
    for trl in limits:
        for resource_name, resource in [
            ("Core", trl.core),
            ("GraphQL", trl.graphql),
            ("Search", trl.search),
        ]:
            pct = resource.utilization_pct
            if pct > 80:
                msg = f"🔴 CRITICAL: {trl.source} {resource_name} at {pct:.1f}%"
                print(msg)
                warnings.append(msg)
                has_warnings = True
            elif pct > 50:
                msg = f"🟡 WARNING: {trl.source} {resource_name} at {pct:.1f}%"
                print(msg)
                warnings.append(msg)
                has_warnings = True

    if not has_warnings:
        print("✅ All tokens within normal ranges (<50%)")

    return warnings


def print_load_balance_analysis(limits: list[TokenRateLimits]) -> None:
    """Analyze load balancing across tokens."""
    print("\n⚖️  LOAD BALANCE ANALYSIS")
    print("-" * 40)

    if len(limits) < 2:
        print(f"⚠️  Only {len(limits)} token(s) available. Consider adding more for redundancy.")
        return

    core_pcts = [trl.core.utilization_pct for trl in limits]
    max_pct = max(core_pcts)
    min_pct = min(core_pcts)
    spread = max_pct - min_pct

    print(f"Tokens available: {len(limits)}")
    print(f"Core API utilization range: {min_pct:.1f}% - {max_pct:.1f}%")
    print(f"Spread: {spread:.1f}%")

    if spread > 30:
        print("⚠️  Load is unevenly distributed. Review workflow token configurations.")
    else:
        print("✅ Load is reasonably balanced across tokens.")


def print_recommendations() -> None:
    """Print recommendations for API rate limit management."""
    print("\n💡 RECOMMENDATIONS")
    print("-" * 40)
    recommendations = [
        "1. GitHub Apps have higher rate limits (5000-15000/hour) than PATs (5000/hour)",
        "2. Use GITHUB_TOKEN for repo-scoped operations (higher limits within Actions)",
        "3. Implement retry logic with exponential backoff for rate-limited requests",
        "4. Use conditional requests (If-None-Match headers) to reduce API consumption",
        "5. Cache API responses where appropriate",
        "6. Consider batching operations to reduce total API calls",
        "7. Use GraphQL for complex queries that would require multiple REST calls",
    ]
    for rec in recommendations:
        print(f"  {rec}")


def print_workflow_activity(summaries: list[dict[str, Any]]) -> None:
    """Print workflow activity summary."""
    if not summaries:
        return
    print("\n📊 WORKFLOW ACTIVITY")
    print("-" * 40)
    for summary in summaries:
        repo = summary.get("repo", "unknown")
        window = summary.get("window_hours", "?")
        recent = summary.get("recent_runs", 0)
        total = summary.get("total_runs", 0)
        print(f"{repo}: {recent} run(s) in last {window}h (total reported: {total})")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze GitHub API rate limits across authentication methods"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--check-repos",
        nargs="*",
        metavar="REPO",
        help="Also check workflow activity in specified repos (owner/repo format)",
    )
    parser.add_argument(
        "--workflow-hours",
        type=int,
        default=1,
        help="Time window (hours) for workflow activity checks (default: 1)",
    )
    parser.add_argument(
        "--pat-env",
        default="CODESPACES_WORKFLOWS",
        help="Environment variable name for PAT token (default: CODESPACES_WORKFLOWS)",
    )
    args = parser.parse_args()

    # Collect tokens to check
    tokens: dict[str, str | None] = {
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
    }

    # Add PAT if available
    pat_token = os.environ.get(args.pat_env)
    if pat_token:
        tokens[args.pat_env] = pat_token
    else:
        print(f"Note: {args.pat_env} not set, skipping PAT analysis", file=sys.stderr)

    # Analyze rate limits
    limits = analyze_rate_limits(tokens)

    if not limits:
        print("Error: Could not retrieve rate limits for any token", file=sys.stderr)
        return 1

    workflow_summaries: list[dict[str, Any]] = []
    if args.check_repos:
        token_for_workflows = next((value for value in tokens.values() if value), None)
        workflow_summaries = summarize_workflow_activity(
            args.check_repos,
            token=token_for_workflows,
            hours=args.workflow_hours,
        )

    if args.json:
        # JSON output for programmatic use
        output = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "tokens": {},
        }
        if workflow_summaries:
            output["workflow_activity"] = workflow_summaries
        for trl in limits:
            output["tokens"][trl.source] = {
                "core": {
                    "limit": trl.core.limit,
                    "remaining": trl.core.remaining,
                    "used": trl.core.used,
                    "utilization_pct": round(trl.core.utilization_pct, 2),
                    "reset": trl.core.reset_time,
                },
                "graphql": {
                    "limit": trl.graphql.limit,
                    "remaining": trl.graphql.remaining,
                    "used": trl.graphql.used,
                    "utilization_pct": round(trl.graphql.utilization_pct, 2),
                    "reset": trl.graphql.reset_time,
                },
                "search": {
                    "limit": trl.search.limit,
                    "remaining": trl.search.remaining,
                    "used": trl.search.used,
                    "utilization_pct": round(trl.search.utilization_pct, 2),
                    "reset": trl.search.reset_time,
                },
            }
        print(json.dumps(output, indent=2))
        return 0

    # Human-readable output
    print_utilization_table(limits)
    warnings = print_warnings(limits)
    print_load_balance_analysis(limits)
    print_recommendations()
    print_workflow_activity(workflow_summaries)

    # Return non-zero if critical warnings
    critical = any("CRITICAL" in w for w in warnings)
    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
