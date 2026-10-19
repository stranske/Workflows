# Historical ensemble input provenance

The committed exploratory ensemble analysis used these inputs in this order:

1. codex-cli-screen.json
2. judge-backend-screen-1.json
3. judge-backend-screen-2.json

That historical analyzer used last-wins duplicate observations. The raw files remain unchanged. In particular the two Muse CLI runs conflict; the corrected analyzer rejects that combined input rather than silently overwriting the earlier invalid/tool-using result. The historical aggregate is not a current authority qualification. Re-analysis requires a declared consistent corpus/prompt fingerprint and one nonconflicting observation per judge/case, preserving raw FAIL separately from CONCERNS. Missing raw verdicts cannot support tie-break claims. Approval additionally requires every configured statistical, category and paired incumbent gate.

## Standard Muse 1.3 current-prompt reconstruction

**Recoverability finding:** per-case *result* rows for standard Muse 1.3 are
recoverable from the public immutable screen file
`muse-spark-1-3-screen.json` at revision
`e888a4b159a8076882c94c5f309b73aee86a13cd` (merged PR #4096). Exact original
prompt *text* is **not** recoverable from any verified public source in this
repository; only recorded per-case input digests are preserved.

`standard-muse13-observations.json` preserves all eight standard Muse 1.3
observations from that screen. The source bytes are pinned by SHA-256; each case
records input digest, source revision, prediction and expected verdict. The only
judge identity transformation qualifies the historical `muse-api` label with its
recorded `served_model=muse-spark-1.3`; no observation is replaced.

`current-prompt-ensemble-policy.json` is a pinned copy of the selection policy
used for the stored authority fields (SHA-256
`0ea8fe30cff376a7fba3cbdbbb30bc5a3d96af8465361b1956d5b759f307e72f`). Replay
passes that policy into `analyze` and never consults live
`config/model_selection_policy.json`. Every ordered input also has a pinned
SHA-256 in `evidence_reproduction.input_sha256`, so a raw-verdict rewrite that
still normalizes to `NON_PASS` cannot pass `--check`.

Run `python -m tools.reproduce_muse13_screen --check` from the repository root.
It regenerates the preserved rows and every result in `current-prompt-ensemble.json`
from six versioned inputs plus the pinned policy: eight cases, nine judges, 36
pairs, 252 tie breaks and 72 failovers. The standard screen remains 4/8 correct,
with two false PASS and two false FAIL decisions. No eligibility or authority
setting changes.

The old `/tmp/judge-screen/muse13-renamed.json` is unnecessary. Use `--write` to
regenerate the artifact and receipt only after the complete stored calculations
match. The focused regression command is
`python -m pytest tests/tools/test_reproduce_muse13_screen.py -q`.

Exact original prompt text is not recovered or published. Public provenance of
that text is unverified; preserved prompt digests alone do not prove reconstruction
of the original inputs. The replay proves reproducibility of the **versioned
observations and aggregate calculations**, without new model calls. It does not
claim fresh model quality, provider identity, or new input observations.

Validation (2026-10-19): `python -m tools.reproduce_muse13_screen --check`
reports `{"cases": 8, "judges": 9, "pairs": 36, "tie_breaks": 252}`.
`python -m pytest tests/tools/test_reproduce_muse13_screen.py -q`: 12 passed.
Peer-input raw rewrites and policy digest changes are rejected. No model request
is made.
