# Historical validation runs for Workflows #3820

The October 2026 source-repair runs left test transcripts, JUnit reports, and
scanner captures. The original paths, manifests and data are in the
[historical evidence snapshot][snapshot].

| Run | Original evidence |
| --- | --- |
| Verifier caller validation | [Repair report][caller], [artifact checksums][caller-artifacts], and command output and scanner captures with the `verifier-caller-security-` prefix |
| Native capacity and context window | [Capacity report][capacity] and [context-window report][context], with the `native-capacity-` and `native-context-window-` validation captures |
| Expanded checkout | [Checkout report][checkout] and `expanded-checkout-*.xml` |
| Original repair, review corrections, and October 10 source merge | [Repair and correction reports][original], [merge report][merge], and their test, mutation, and template-validation output |
| Capture failure CLI boundary | [Original run folder][capture] with the CLI verdict results, mutation receipt and test output |
| Diff snapshot identity | [Original run folder][diff] with the input identity proof and test output |
| Grouped shared-span joins | [Original run folder][joins] with the failing, restored, and template-validation transcripts |

## Recover the original paths

Use a clone with the snapshot revision. If your clone is shallow, fetch full
history first with `git fetch --unshallow origin`. Extract to a new directory
to keep the current checkout separate. Evidence paths and checksum keys are
relative to the export's root. Rerun a recorded validation command from a
checkout of the source revision identified in its report.

```sh
set -o pipefail
out=$(mktemp -d)
git archive 3c84badc9c7859de9f9c97b47fe45c77200fde13 evidence/issue-3820 | tar -xf - -C "$out"
printf '%s\n' "$out/evidence/issue-3820"
```

[snapshot]: https://github.com/stranske/Workflows/tree/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820
[caller]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/verifier-caller-security-repair.md
[caller-artifacts]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/verifier-caller-security-artifacts.json
[capacity]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/native-capacity-recovery.md
[context]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/native-context-window-repair.md
[checkout]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/expanded-checkout-repair.md
[original]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/README.md
[merge]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/20261010-source-merge-recovery.md
[capture]: https://github.com/stranske/Workflows/tree/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/capture-failure-boundary-20261011
[diff]: https://github.com/stranske/Workflows/tree/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/diff-snapshot-binding-20261011
[joins]: https://github.com/stranske/Workflows/tree/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/grouped-shared-joins
