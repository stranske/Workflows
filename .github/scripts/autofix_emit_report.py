"""Write the autofix JSON report consumed by downstream jobs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class AutofixContext:
    output_path: Path
    enriched_path: Path
    pr_number: str | None
    mode: str
    changed: str
    remaining: str
    new: str
    file_list_raw: str

    @property
    def file_list(self) -> list[str]:
        return [line.strip() for line in self.file_list_raw.splitlines() if line.strip()]


def load_enriched(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def build_report(ctx: AutofixContext) -> dict:
    report = load_enriched(ctx.enriched_path)
    if report is not None:
        report.update(
            {
                "pull_request": ctx.pr_number,
                "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        return report

    return {
        "mode": ctx.mode,
        "changed": ctx.changed,
        "remaining_issues": ctx.remaining,
        "new_issues": ctx.new,
        "file_list": ctx.file_list,
    }


def write_report(report: dict, destination: Path) -> None:
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_context() -> AutofixContext:
    return AutofixContext(
        output_path=Path(os.environ.get("AUTOFIX_REPORT", "autofix_report.json")),
        enriched_path=Path(
            os.environ.get("AUTOFIX_REPORT_ENRICHED", "autofix_report_enriched.json")
        ),
        pr_number=os.environ.get("PR_NUMBER"),
        mode=os.environ.get("REPORT_MODE", ""),
        changed=os.environ.get("REPORT_CHANGED", ""),
        remaining=os.environ.get("REPORT_REMAINING", ""),
        new=os.environ.get("REPORT_NEW", ""),
        file_list_raw=os.environ.get("REPORT_FILE_LIST", ""),
    )


def main() -> None:
    ctx = build_context()
    write_report(build_report(ctx), ctx.output_path)


if __name__ == "__main__":
    main()
