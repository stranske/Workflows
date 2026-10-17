#!/usr/bin/env python3
"""Replay archived A/B/C/D evaluator prompts through a candidate judge and score it against the record.

Pilot 4 of the agy guide. An archived experiment directory holds, per evaluator, the exact prompt it
received (``eval-prompt-<judge>.txt``), its raw output (``eval-out-<judge>.txt``) and the map from
anonymised letters to implementation members (``eval-maps.json``). The candidate judge gets one of
those prompts, so it sees exactly what the real judges saw, and its scores are compared with theirs.

Measure: mean absolute error of the candidate's per-member scores against the mean of the real
judges' scores for the same members, beside each real judge's error against the mean of the OTHER
real judges (the yardstick: what a good judge looks like on the same experiment), plus rank
agreement. This is the shape of the Orchestrator's ``judge_reliability`` consensus error, but it is a
replay on archived work: **it writes nothing to the Brain and does not make a judge ``ready``**. A
judge earns weight only by being fielded and scored in real experiments.

The candidate never gets tools (``agy_pilot.agy_backend`` runs ``--mode plan`` in a scratch dir).
Only aggregate numbers are reported; no prompt text or path is written to the result file.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from tools.agy_pilot import Backend, agy_backend, claude_backend

SCHEMA = "workflows-agy-judge-replay/v1"


def parse_scores(text: str) -> dict[str, float] | None:
    """The last JSON object in ``text`` that carries a ``scores`` mapping of letter -> number."""
    found = None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        scores = candidate.get("scores") if isinstance(candidate, dict) else None
        if isinstance(scores, dict) and scores:
            try:
                found = {str(k): float(v) for k, v in scores.items()}
            except (TypeError, ValueError):
                continue
    return found


def load_experiment(path: Path) -> dict | None:
    maps_file = path / "eval-maps.json"
    if not maps_file.exists():
        return None
    maps = json.loads(maps_file.read_text())
    prompts, real = {}, {}
    for judge, letters in maps.items():
        prompt_file, out_file = path / f"eval-prompt-{judge}.txt", path / f"eval-out-{judge}.txt"
        if prompt_file.exists():
            prompts[judge] = prompt_file.read_text()
        if out_file.exists():
            scores = parse_scores(out_file.read_text())
            if scores:
                real[judge] = member_scores(scores, letters)
    return {"maps": maps, "prompts": prompts, "real": real}


def member_scores(scores: dict[str, float], letters: dict[str, str]) -> dict[str, float]:
    return {letters[k]: v for k, v in scores.items() if k in letters}


def consensus(judges: list[dict[str, float]]) -> dict[str, float]:
    members = set().union(*judges) if judges else set()
    return {m: statistics.fmean(j[m] for j in judges if m in j) for m in members}


def mae(a: dict[str, float], b: dict[str, float]) -> float | None:
    shared = [m for m in a if m in b]
    return statistics.fmean(abs(a[m] - b[m]) for m in shared) if shared else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    shared = sorted(m for m in a if m in b)
    if len(shared) < 3:
        return None
    ra, rb = _ranks([a[m] for m in shared]), _ranks([b[m] for m in shared])
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return None if den == 0 else num / den


def replay_experiment(experiment: dict, backend: Backend, prompt_judge: str | None = None) -> dict:
    """One replay: the candidate sees ``prompt_judge``'s prompt (default: first with a real score)."""
    real = experiment["real"]
    judge = prompt_judge or next((j for j in experiment["prompts"] if j in real), None)
    if len(real) < 3 or judge is None:
        return {"usable": False, "reason": "needs at least 3 scored real judges and a prompt"}
    call = backend(experiment["prompts"][judge])
    scores = parse_scores(call.text) if call.text.strip() and not call.error else None
    if scores is None:
        return {
            "usable": False,
            "reason": call.error or "no parseable scores",
            "tokens_in": call.tokens_in,
        }
    candidate = member_scores(scores, experiment["maps"][judge])
    yard = [mae(real[j], consensus([real[o] for o in real if o != j])) for j in real]
    yard = [y for y in yard if y is not None]
    return {
        "usable": True,
        "members_scored": len(candidate),
        "candidate_mae": mae(candidate, consensus(list(real.values()))),
        "candidate_rank_corr": spearman(candidate, consensus(list(real.values()))),
        "real_judges_mae_mean": statistics.fmean(yard) if yard else None,
        "real_judges": len(real),
        "tokens_in": call.tokens_in,
        "tokens_out": call.tokens_out,
    }


def summarise(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("usable")]
    pick = lambda key: [r[key] for r in ok if r.get(key) is not None]  # noqa: E731
    cand, yard = pick("candidate_mae"), pick("real_judges_mae_mean")
    corr = pick("candidate_rank_corr")
    return {
        "experiments": len(rows),
        "usable": len(ok),
        "candidate_mae_mean": round(statistics.fmean(cand), 3) if cand else None,
        "real_judges_mae_mean": round(statistics.fmean(yard), 3) if yard else None,
        "candidate_rank_corr_mean": round(statistics.fmean(corr), 3) if corr else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", nargs="+", type=Path, required=True)
    parser.add_argument("--backend", choices=("agy", "claude"), default="agy")
    parser.add_argument("--agy-model", default="gemini-4-argon-medium")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    backend = agy_backend(args.agy_model) if args.backend == "agy" else claude_backend()
    rows = []
    for path in args.experiments:
        experiment = load_experiment(path)
        rows.append(
            {"experiment": path.name, **replay_experiment(experiment, backend)}
            if experiment
            else {"experiment": path.name, "usable": False, "reason": "no eval-maps.json"}
        )
    result = {"schema": SCHEMA, "backend": args.backend, "summary": summarise(rows), "rows": rows}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
