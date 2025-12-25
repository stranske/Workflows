"""PR metrics tracking and analysis utilities.

Track pull request metrics like time-to-merge, review cycles, and autofix success.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PRMetrics:
    """Metrics for a single pull request."""

    pr_number: int
    created_at: datetime
    merged_at: Optional[datetime]
    review_count: int
    commit_count: int
    autofix_applied: bool
    labels: List[str]

    def time_to_merge_hours(self) -> Optional[float]:
        """Calculate hours from creation to merge."""
        if self.merged_at is None:
            return None
        delta = self.merged_at - self.created_at
        return delta.total_seconds() / 3600


def parse_pr_data(data: Dict[str, Any]) -> PRMetrics:
    """Parse PR data from GitHub API response.

    Args:
        data: GitHub PR API response

    Returns:
        PRMetrics instance
    """
    created = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    merged = None
    if data.get("merged_at"):
        merged = datetime.fromisoformat(data["merged_at"].replace("Z", "+00:00"))

    labels = [label["name"] for label in data.get("labels", [])]
    autofix = any("autofix" in label for label in labels)

    return PRMetrics(
        pr_number=data["number"],
        created_at=created,
        merged_at=merged,
        review_count=data.get("review_comments", 0),
        commit_count=data.get("commits", 1),
        autofix_applied=autofix,
        labels=labels,
    )


def load_pr_history(path: str) -> List[PRMetrics]:
    """Load PR metrics history from NDJSON file.

    Args:
        path: Path to history file

    Returns:
        List of PRMetrics instances
    """
    metrics: List[PRMetrics] = []
    history_path = Path(path)

    if not history_path.exists():
        return metrics

    with open(history_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                metrics.append(parse_pr_data(data))
            except (json.JSONDecodeError, KeyError):
                continue

    return metrics


def calculate_average_merge_time(metrics: List[PRMetrics]) -> float:
    """Calculate average time to merge in hours.

    Args:
        metrics: List of PR metrics

    Returns:
        Average hours to merge (0.0 if no merged PRs)
    """
    merge_times = []
    for pr in metrics:
        time = pr.time_to_merge_hours()
        if time is not None:
            merge_times.append(time)

    if not merge_times:
        return 0.0

    return sum(merge_times) / len(merge_times)


def calculate_autofix_rate(metrics: List[PRMetrics]) -> float:
    """Calculate percentage of PRs with autofix applied.

    Args:
        metrics: List of PR metrics

    Returns:
        Autofix rate as percentage (0.0-100.0)
    """
    if not metrics:
        return 0.0

    autofix_count = sum(1 for pr in metrics if pr.autofix_applied)
    return (autofix_count / len(metrics)) * 100


def group_by_label(metrics: List[PRMetrics]) -> Dict[str, List[PRMetrics]]:
    """Group PRs by their labels.

    Args:
        metrics: List of PR metrics

    Returns:
        Dictionary mapping label to list of PRs
    """
    grouped: Dict[str, List[PRMetrics]] = {}

    for pr in metrics:
        for label in pr.labels:
            if label not in grouped:
                grouped[label] = []
            grouped[label].append(pr)

    return grouped


def generate_metrics_summary(metrics: List[PRMetrics]) -> Dict[str, Any]:
    """Generate a summary of PR metrics.

    Args:
        metrics: List of PR metrics

    Returns:
        Summary dictionary
    """
    merged = [pr for pr in metrics if pr.merged_at is not None]

    return {
        "total_prs": len(metrics),
        "merged_prs": len(merged),
        "avg_merge_time_hours": calculate_average_merge_time(metrics),
        "autofix_rate_percent": calculate_autofix_rate(metrics),
        "avg_review_count": sum(pr.review_count for pr in metrics) / max(len(metrics), 1),
        "avg_commit_count": sum(pr.commit_count for pr in metrics) / max(len(metrics), 1),
    }
