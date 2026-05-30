"""Generic input-coverage manifest.

The app supplies:
  * ``all_keys``      -- every input parameter (from a JSON schema, Pydantic /
                         dataclass fields, etc.)
  * ``touched_keys``  -- the keys exercised by at least one catalog scenario
  * ``priority_params`` -- the must-cover subset
  * ``read_keys``     -- (optional) keys observed read at runtime

The manifest computes coverage, flags typos (catalog keys absent from the
schema) and priority gaps, and renders a markdown report for the issue
automation to consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CoverageManifest:
    all_keys: set[str]
    touched_keys: set[str]
    priority_params: list[str] = field(default_factory=list)
    read_keys: set[str] = field(default_factory=set)
    title: str = "Baseline coverage manifest"

    @property
    def unknown_catalog_keys(self) -> set[str]:
        return {k for k in self.touched_keys if k not in self.all_keys}

    @property
    def priority_gaps(self) -> list[str]:
        return [p for p in self.priority_params if p not in self.touched_keys]

    @property
    def coverage_pct(self) -> float:
        if not self.all_keys:
            return 0.0
        return 100.0 * len(self.touched_keys & self.all_keys) / len(self.all_keys)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            f"- Input parameters: **{len(self.all_keys)}**",
            f"- Exercised by a scenario: **{len(self.touched_keys & self.all_keys)}** "
            f"({self.coverage_pct:.1f}%)",
            f"- Observed read at runtime: **{len(self.read_keys)}**",
            "",
            "## Priority parameters",
            "",
        ]
        for p in self.priority_params:
            lines.append(f"- [{'x' if p in self.touched_keys else ' '}] `{p}`")
        if self.priority_gaps:
            lines += ["", "## Priority gaps (no scenario yet)", ""]
            lines += [f"- `{p}`" for p in self.priority_gaps]
        if self.unknown_catalog_keys:
            lines += ["", "## Catalog keys not found in schema (check spelling)", ""]
            lines += [f"- `{k}`" for k in sorted(self.unknown_catalog_keys)]
        return "\n".join(lines) + "\n"
