# Historical ensemble input provenance

The committed exploratory ensemble analysis used these inputs in this order:

1. codex-cli-screen.json
2. judge-backend-screen-1.json
3. judge-backend-screen-2.json

That historical analyzer used last-wins duplicate observations. The raw files remain unchanged. In particular the two Muse CLI runs conflict; the corrected analyzer rejects that combined input rather than silently overwriting the earlier invalid/tool-using result. The historical aggregate is not a current authority qualification. Re-analysis requires a declared consistent corpus/prompt fingerprint and one nonconflicting observation per judge/case, preserving raw FAIL separately from CONCERNS. Missing raw verdicts cannot support tie-break claims. Approval additionally requires every configured statistical, category and paired incumbent gate.

## Ensemble report recovery

The [historical seven-judge report](https://github.com/stranske/Workflows/blob/59d75176da68a2a592ea0a2740382c9453d69b02/docs/evidence/judge-screen-20261017/ensemble-analysis.md) and its [machine-readable aggregate](https://github.com/stranske/Workflows/blob/59d75176da68a2a592ea0a2740382c9453d69b02/docs/evidence/judge-screen-20261017/ensemble-analysis.json) preserve the original last-wins result described above. The [current-prompt nine-judge report](https://github.com/stranske/Workflows/blob/59d75176da68a2a592ea0a2740382c9453d69b02/docs/evidence/judge-screen-20261017/current-prompt-ensemble.md) contains its full pair table and reproduction appendix. The [current-prompt JSON](current-prompt-ensemble.json) is used by the offline replay below.

The [offline archive](approval-set-57.tar.gz) holds exact copies of the three reports under `reports/` alongside the original six approval screens. From the repository root, recover the reports without Git history or network access. The last line prints the directory containing the recovered files. The copied provenance page links to the original JSON, archive, and standards analysis through the checkout. Run the appendix’s replay command from the repository root.

```sh
(
  set -eu
  checkout=$(pwd -P)
  directory=docs/evidence/judge-screen-20261017
  packet=$directory/approval-set-57.tar.gz
  printf '%s  %s\n' 33896497b671e25380b8c139a398d44a2720cfab6dc192972fc1c7a8617a4f58 "$packet" | shasum -a 256 -c -
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/workflows-ensemble-reports.XXXXXXXX")
  output=$recovered/$directory
  mkdir -p "$output"
  tar --strip-components=1 -xpzf "$packet" -C "$output" \
    reports/ensemble-analysis.json reports/ensemble-analysis.md reports/current-prompt-ensemble.md
  cd "$output"
  shasum -a 256 -c <<'SUMS'
763b3063404c2bff4529dc1155419e581f7ccc0634dc7b17723a55a6db2e45d6  ensemble-analysis.json
7c00458106c6c1cb3fc90d9adb61924640dfdc16079b9f34f904a630f8294706  ensemble-analysis.md
7a93c1874df41fcf8a986611237b881cd0ca575bdb8a511729fae62243f02664  current-prompt-ensemble.md
SUMS
  cp "$checkout/$directory/PROVENANCE.md" .
  ln -s "$checkout/$packet" "$checkout/$directory/current-prompt-ensemble.json" .
  ln -s "$checkout/docs/ops" "$recovered/docs/ops"
  pwd
)
```

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

## October 17 approval-set and pilot results

The six judges each evaluated the same 57 cases. Section 3 of the [standards analysis](../../ops/VERIFIER_STANDARDS_ANALYSIS.md) uses the 35 cases left after excluding the 22 failed-CI controls. The earlier 18-case pilot has six separate files matching `pilot-18-*.json` in this directory.

[Browse the original six JSON files](https://github.com/stranske/Workflows/tree/33dc30842c744c2ff3904dedbbfd4bcbc1975050/docs/evidence/judge-screen-20261017) or [download the offline archive](approval-set-57.tar.gz). From the repository root, extract the approval-set files to a fresh directory and verify their original bytes.

```sh
(
  set -eu
  packet=docs/evidence/judge-screen-20261017/approval-set-57.tar.gz
  printf '%s  %s\n' 33896497b671e25380b8c139a398d44a2720cfab6dc192972fc1c7a8617a4f58 "$packet" | shasum -a 256 -c -
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/workflows-approval-set.XXXXXXXX")
  tar -xpzf "$packet" -C "$recovered" \
    approval-set-57-claude.json approval-set-57-cursor.json approval-set-57-luna.json \
    approval-set-57-muse12.json approval-set-57-muse12c.json approval-set-57-terra.json
  cd "$recovered"
  shasum -a 256 -c <<'SUMS'
8555f8d0d6a399208fb0deedb19957713773098885b4d840343ff9af86a4d5d8  approval-set-57-claude.json
66aca961dabfc6ff980a7338c21e081929e8e1b5e17c71b081a235d6a1dbce17  approval-set-57-cursor.json
21bbedd38809fbf46f96ff16e552b0b2d5d2572e4d7216c535b57050e0807b82  approval-set-57-luna.json
2bfa28b0f543fc6751fd841d2925a5e426d8f5954c1661b7aae40caa5168ed86  approval-set-57-muse12.json
eca0ff2ba9630249fe6e8b6effebc07a93010c52cce1081d4f7e7d33c141f16f  approval-set-57-muse12c.json
bc7a2e6dc1ed8b054a9af3cca7388f515405df937496d14166ed3a5284b285cb  approval-set-57-terra.json
SUMS
  pwd
)
```
