#!/usr/bin/env python3
"""Seeded-defect pilots for a candidate coding agent (agy first): audit recall and test generation.

Ground truth is machine-made, so no owner time is needed. A small stdlib-only module that already has
a test suite is mutated (an operator flip, an off-by-one, a negation). A mutant is kept only if the
module's OWN tests fail on it, which proves it is a behavioural defect and not noise. Then:

* **audit** (read-only): the model reads the module with all kept mutants applied and returns the
  defective lines. Score: recall of the seeded lines (within a line tolerance), precision, and the
  share of cited lines that exist.
* **testgen**: the model reads the CLEAN module and returns a pytest file as text (nothing is written
  by the model). The file must pass on the clean module; its score is the share of mutants it kills.

Each job runs twice, one call per module (single) and one call for several modules (batched), so
units per item and empty-result failures are measured on the same work (Workflows agy guide, pilots 3
and 5, option 6). Tokens are reported as the backend states them; a backend that reports none is
shown as ``None``, never estimated. Models never get tools: agy runs ``--mode plan`` in a scratch
directory, Claude runs with every tool disabled.

This is exploratory evidence from a handful of modules. It can rank candidates against an incumbent
on the same work; it cannot approve a candidate for anything.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import subprocess
import sys
import tempfile
import time
import tokenize
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tools.run_judge_backend_screen import _clean_env, _int, _ms

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "workflows-agy-pilot/v1"
LINE_TOLERANCE = 1

_SWAPS = {
    "==": "!=",
    "!=": "==",
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "+": "-",
    "-": "+",
    "and": "or",
    "or": "and",
    "True": "False",
    "False": "True",
}


@dataclass(frozen=True)
class Mutant:
    line: int
    original: str
    mutated: str
    source: str  # the full module text with this single change


@dataclass
class Target:
    name: str
    source: str
    tests: Path
    mutants: list[Mutant] = field(default_factory=list)


@dataclass
class ModelCall:
    text: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: float = 0.0
    error: str | None = None


Backend = Callable[[str], ModelCall]


# ---------------------------------------------------------------- mutants


def candidate_mutants(source: str) -> list[Mutant]:
    """Every single-token mutation of operators and boolean literals, outside strings and comments."""
    lines = source.splitlines(keepends=True)
    found: list[Mutant] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type not in (tokenize.OP, tokenize.NAME) or tok.string not in _SWAPS:
            continue
        (row, col), (_, end) = tok.start, tok.end
        # a unary minus or an operator in a def/class header is not a stable behavioural change
        if tok.string in "+-" and lines[row - 1][:col].strip() in ("", "(", ",", "="):
            continue
        if lines[row - 1].lstrip().startswith(("def ", "class ", "import ", "from ", "@")):
            continue
        new = _SWAPS[tok.string]
        mutated_line = lines[row - 1][:col] + new + lines[row - 1][end:]
        text = "".join(lines[: row - 1] + [mutated_line] + lines[row:])
        found.append(Mutant(row, tok.string, new, text))
    return found


def _run_pytest(module_name: str, module_source: str, tests: str, timeout: int = 120) -> bool:
    """True when `tests` (a pytest file text) passes against `module_source` in a scratch dir."""
    with tempfile.TemporaryDirectory(prefix="agy-pilot-") as scratch:
        package = Path(scratch) / "tools"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / f"{module_name}.py").write_text(module_source)
        (Path(scratch) / f"test_{module_name}_pilot.py").write_text(tests)
        try:
            run = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", scratch],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=scratch,
                env=_clean_env(),
            )
        except subprocess.TimeoutExpired:
            return False
        return run.returncode == 0


def validated_mutants(
    name: str, source: str, test_text: str, count: int, seed: int
) -> list[Mutant]:
    """Pick up to `count` mutants that the module's own tests fail on (a real behavioural change).

    Returns [] when the module's own tests do not pass on the clean source in the scratch layout,
    because then no kill result means anything.
    """
    if not _run_pytest(name, source, test_text):
        return []
    pool = candidate_mutants(source)
    random.Random(seed).shuffle(pool)
    kept: list[Mutant] = []
    used_lines: set[int] = set()
    for mutant in pool:
        if len(kept) >= count:
            break
        if mutant.line in used_lines:
            continue
        if not _run_pytest(name, mutant.source, test_text):
            kept.append(mutant)
            used_lines.add(mutant.line)
    return sorted(kept, key=lambda m: m.line)


def apply_all(source: str, mutants: list[Mutant]) -> str:
    lines = source.splitlines(keepends=True)
    for mutant in mutants:
        lines[mutant.line - 1] = mutant.source.splitlines(keepends=True)[mutant.line - 1]
    return "".join(lines)


# ---------------------------------------------------------------- prompts and parsing


def _numbered(source: str) -> str:
    return "\n".join(f"{n:4d}  {line}" for n, line in enumerate(source.splitlines(), 1))


def audit_prompt(items: list[tuple[str, str]]) -> str:
    body = "\n\n".join(f"### module: {name}\n{_numbered(src)}" for name, src in items)
    return (
        "You are auditing Python modules for behavioural defects (wrong operator, inverted condition, "
        "off-by-one, wrong boolean). Do not use tools; the code is below with line numbers. Report "
        "only real defects, each with the module, the 1-based line number and a one-sentence reason. "
        'Reply with ONE JSON object only: {"findings":[{"module":"<name>","line":<int>,"issue":"<text>"}]}\n\n'
        + body
    )


def testgen_prompt(items: list[tuple[str, str]]) -> str:
    body = "\n\n".join(f"### module: {name}\n{src}" for name, src in items)
    return (
        "Write a pytest test file for each Python module below. Do not use tools. Each test file "
        "imports the module as `from tools import <module>` (for example `from tools import integration_repo`), uses only the "
        "standard library and pytest, and must PASS on the code as given. Make the tests sensitive: "
        "they should fail if any operator, comparison or boolean in the module were changed. Reply "
        'with ONE JSON object only: {"tests":{"<module>":"<full test file text>"}}\n\n' + body
    )


def parse_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


# ---------------------------------------------------------------- scoring


def score_audit(findings: list[dict], target: Target) -> dict:
    """Recall of seeded lines, precision, and share of cited lines that exist, for one module."""
    own = [f for f in findings if str(f.get("module")) == target.name]
    n_lines = len(target.source.splitlines())
    lines = []
    for finding in own:
        try:
            lines.append(int(finding.get("line")))
        except (TypeError, ValueError):
            continue
    seeded = [m.line for m in target.mutants]
    hit = {s for s in seeded if any(abs(s - c) <= LINE_TOLERANCE for c in lines)}
    useful = [c for c in lines if any(abs(s - c) <= LINE_TOLERANCE for s in seeded)]
    return {
        "seeded": len(seeded),
        "found": len(hit),
        "reported": len(lines),
        "useful": len(useful),
        "resolving": sum(1 <= c <= n_lines for c in lines),
    }


def score_testgen(tests: str | None, target: Target) -> dict:
    """The generated file must pass on clean code; then the share of mutants it kills."""
    if not tests or not tests.strip():
        return {"mutants": len(target.mutants), "killed": 0, "clean_pass": False}
    clean = _run_pytest(target.name, target.source, tests)
    killed = (
        sum(not _run_pytest(target.name, m.source, tests) for m in target.mutants) if clean else 0
    )
    return {"mutants": len(target.mutants), "killed": killed, "clean_pass": clean}


# ---------------------------------------------------------------- running


def run_pilot(
    backend: Backend, targets: list[Target], kind: str, mode: str, batch_size: int
) -> dict:
    """One backend, one kind (audit|testgen), one mode (single|batched). Returns per-module scores."""
    groups = (
        [[t] for t in targets]
        if mode == "single"
        else [targets[i : i + batch_size] for i in range(0, len(targets), batch_size)]
    )
    calls, scores = [], []
    for group in groups:
        if kind == "audit":
            items = [(t.name, apply_all(t.source, t.mutants)) for t in group]
            call = backend(audit_prompt(items))
        else:
            call = backend(testgen_prompt([(t.name, t.source) for t in group]))
        calls.append(call)
        parsed = parse_json_object(call.text) if call.text.strip() and not call.error else None
        for target in group:
            if kind == "audit":
                raw = (parsed or {}).get("findings")
                findings = raw if isinstance(raw, list) else []
                row = score_audit([f for f in findings if isinstance(f, dict)], target)
            else:
                tests = ((parsed or {}).get("tests") or {}).get(target.name)
                row = score_testgen(tests if isinstance(tests, str) else None, target)
            scores.append({"module": target.name, "usable": parsed is not None, **row})
    tokens_in = [c.tokens_in for c in calls]
    tokens_out = [c.tokens_out for c in calls]
    items_done = len(targets)
    return {
        "kind": kind,
        "mode": mode,
        "calls": len(calls),
        "items": items_done,
        "empty_or_unusable": sum(1 for s in scores if not s["usable"]),
        "errors": sorted({c.error for c in calls if c.error}),
        "tokens_in": None if None in tokens_in else sum(tokens_in),
        "tokens_out": None if None in tokens_out else sum(tokens_out),
        "tokens_per_item": (
            None
            if None in tokens_in or None in tokens_out
            else round((sum(tokens_in) + sum(tokens_out)) / max(1, items_done))
        ),
        "latency_s": round(sum(c.latency_ms for c in calls) / 1000, 1),
        "scores": scores,
        "totals": _totals(kind, scores),
    }


def _totals(kind: str, scores: list[dict]) -> dict:
    if kind == "audit":
        seeded = sum(s.get("seeded", 0) for s in scores)
        reported = sum(s.get("reported", 0) for s in scores)
        return {
            "recall": round(sum(s.get("found", 0) for s in scores) / seeded, 3) if seeded else None,
            "precision": (
                round(sum(s.get("useful", 0) for s in scores) / reported, 3) if reported else None
            ),
            "citations_resolving": (
                round(sum(s.get("resolving", 0) for s in scores) / reported, 3)
                if reported
                else None
            ),
        }
    mutants = sum(s.get("mutants", 0) for s in scores)
    return {
        "kill_rate": (
            round(sum(s.get("killed", 0) for s in scores) / mutants, 3) if mutants else None
        ),
        "clean_pass_rate": (
            round(sum(bool(s.get("clean_pass")) for s in scores) / len(scores), 3)
            if scores
            else None
        ),
    }


# ---------------------------------------------------------------- backends


def agy_backend(model: str, timeout: int = 480, agy: str = "agy") -> Backend:
    def call(prompt: str) -> ModelCall:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="pilot-agy-") as scratch:
            command = [
                agy,
                "--gemini_dir",
                str(Path(scratch) / ".gemini"),
                "-p",
                prompt,
                "--output-format",
                "json",
                "--model",
                model,
                "--mode",
                "plan",
                "--add-dir",
                scratch,
                "--print-timeout",
                f"{timeout // 60}m",
            ]
            try:
                run = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=timeout + 60,
                    check=False,
                    env=_clean_env(),
                )
            except subprocess.TimeoutExpired:
                return ModelCall(error="agy timed out", latency_ms=_ms(started))
        try:
            envelope = json.loads(run.stdout)
        except ValueError:
            return ModelCall(
                error=f"agy output was not JSON (rc {run.returncode})", latency_ms=_ms(started)
            )
        usage = envelope.get("usage") or {}
        text = str(envelope.get("response") or "")
        error = (
            None
            if (not run.returncode and envelope.get("status") == "SUCCESS" and text.strip())
            else (
                "agy returned an empty response"
                if not text.strip()
                else f"agy status {envelope.get('status')}"
            )
        )
        return ModelCall(
            text,
            _int(usage.get("input_tokens")),
            _int(usage.get("output_tokens")),
            _ms(started),
            error,
        )

    return call


def claude_backend(model: str | None = None, timeout: int = 420, claude: str = "claude") -> Backend:
    def call(prompt: str) -> ModelCall:
        started = time.perf_counter()
        command = [
            claude,
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--setting-sources",
            "",
        ]
        if model:
            command += ["--model", model]
        with tempfile.TemporaryDirectory(prefix="pilot-claude-") as scratch:
            try:
                run = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=timeout,
                    check=False,
                    env=_clean_env({"CLAUDE_CODE_OAUTH_TOKEN"}),
                )
            except subprocess.TimeoutExpired:
                return ModelCall(error="Claude CLI timed out", latency_ms=_ms(started))
        try:
            envelope = json.loads(run.stdout)
        except ValueError:
            return ModelCall(
                error=f"Claude CLI output was not JSON (rc {run.returncode})",
                latency_ms=_ms(started),
            )
        usage = envelope.get("usage") or {}
        tokens_in = (
            sum(
                _int(usage.get(k)) or 0
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
            or None
        )
        error = "Claude CLI error" if (run.returncode or envelope.get("is_error")) else None
        return ModelCall(
            str(envelope.get("result") or ""),
            tokens_in,
            _int(usage.get("output_tokens")),
            _ms(started),
            error,
        )

    return call


# ---------------------------------------------------------------- CLI


def load_targets(paths: list[Path], count: int, seed: int) -> list[Target]:
    targets = []
    for path in paths:
        name = path.stem
        tests = ROOT / "tests" / "tools" / f"test_{name}.py"
        source = path.read_text()
        test_text = tests.read_text() if tests.exists() else ""
        mutants = validated_mutants(name, source, test_text, count, seed) if test_text else []
        if mutants:
            targets.append(Target(name, source, tests, mutants))
        else:
            print(f"skipped {name}: no validated mutants", file=sys.stderr)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", nargs="+", type=Path, required=True)
    parser.add_argument("--backends", default="agy,claude")
    parser.add_argument("--agy-model", default="gemini-4-argon-medium")
    parser.add_argument("--claude-model")
    parser.add_argument("--kinds", default="audit,testgen")
    parser.add_argument("--modes", default="single,batched")
    parser.add_argument("--mutants", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    targets = load_targets(
        [p if p.is_absolute() else ROOT / p for p in args.modules], args.mutants, args.seed
    )
    if not targets:
        raise SystemExit("no target had validated mutants")
    available = {
        "agy": lambda: agy_backend(args.agy_model),
        "claude": lambda: claude_backend(args.claude_model),
    }
    results = []
    for name in [b.strip() for b in args.backends.split(",") if b.strip()]:
        backend = available[name]()
        for kind in args.kinds.split(","):
            for mode in args.modes.split(","):
                result = run_pilot(backend, targets, kind, mode, args.batch_size)
                results.append({"backend": name, **result})
                print(
                    name,
                    kind,
                    mode,
                    result["totals"],
                    "tokens/item",
                    result["tokens_per_item"],
                    "unusable",
                    result["empty_or_unusable"],
                    flush=True,
                )
    args.output.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "evidence_class": "exploratory-cli-seeded-defects",
                "modules": [
                    {
                        "name": t.name,
                        "mutants": [
                            {"line": m.line, "from": m.original, "to": m.mutated} for m in t.mutants
                        ],
                    }
                    for t in targets
                ],
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
