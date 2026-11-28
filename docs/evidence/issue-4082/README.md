# Gate trigger campaign reconciliation

[Workflows #4082](https://github.com/stranske/Workflows/issues/4082) tracked the create-only Gate trigger rollout. The six November 6–7 campaign readbacks share one [offline archive](campaign-reconciliation-rounds.tar.gz). Each original receipt is also available directly at the pinned revision below.

From the repository root, extract into a fresh directory and check every receipt against the bundled SHA-256 manifest. The archive retains the original repository-relative paths.

```bash
restored=$(mktemp -d) &&
  tar -xzf docs/evidence/issue-4082/campaign-reconciliation-rounds.tar.gz -C "$restored" &&
  (cd "$restored" && shasum -a 256 -c SHA256SUMS)
```

## Round 2

Campaign PR heads and paginated changed-file evidence. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-2.json)

## Round 3

PR metadata and the Portable Alpha Gate patch. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-3.json)

## Round 4

Updated PR metadata and a fresh read of the same Portable Alpha Gate patch. The `portableAlphaDiff` values in rounds 3 and 4 agree and record the removal of `labeled` from the five-event trigger list. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-4.json)

## Round 5

PR status and the consumer patch readback. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-5.json)

## Round 6

Campaign merge readback, default-branch triggers, runner checks and the observation status at that round. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-6.json)

## Round 7

Campaign and default-branch readback. The receipt records the observation completion time and counts as unknown. [Original receipt](https://github.com/stranske/Workflows/blob/b95fcb6b37804032d7fd9197409d5748de8387da/docs/evidence/issue-4082/campaign-reconciliation-round-7.json)

## Historical campaign notes and receipts

The [final verification summary](VERIFICATION_SUMMARY_4522.md) records the
delivered Gate trigger and observed results. The [historical campaign
snapshot](https://github.com/stranske/Workflows/tree/1e4114dc96808a104e0b07e001fa9a1cecaae8d7/docs/evidence/issue-4082)
preserves the implementation and test notes, round-by-round draft comments and
PR descriptions, interim drift results, and reconciliation receipts.

Run this command from a Workflows checkout. It fetches the publishing revision
when needed and prints a fresh temporary directory with the original
repository-relative paths.

```bash
(
  set -e
  revision=1e4114dc96808a104e0b07e001fa9a1cecaae8d7
  directory=docs/evidence/issue-4082
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 origin "$revision"
  fi
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/issue-4082-history.XXXXXX")
  git archive --output="$recovered/evidence.tar" "$revision" -- "$directory"
  tar -xf "$recovered/evidence.tar" -C "$recovered"
  rm "$recovered/evidence.tar"
  printf '%s\n' "$recovered"
)
```
