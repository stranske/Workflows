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
| Source pagination, capture accounting, and replay | [Pagination repair][pagination], [capture integration][capture-integration], and [governing-plan RED/GREEN][governing-plan] |
| Capture failure CLI boundary | [Original run folder][capture] with the CLI verdict results, mutation receipt and test output |
| Diff snapshot identity | [Original run folder][diff] with the input identity proof and test output |
| Grouped shared-span joins | [Original run folder][joins] with the failing, restored, and template-validation transcripts |

## Recover the original paths

Run from any directory inside a Workflows checkout. The command fetches the
pinned snapshot from the publishing repository when needed and prints a new
directory containing the original paths and modes.
Checksums use paths relative to the export root. Commands in a historical
report refer to the source revision named in that report.

```bash
(
  set -e
  revision=3c84badc9c7859de9f9c97b47fe45c77200fde13
  directory=evidence/issue-3820
  if [ "$(git rev-parse --is-bare-repository)" = false ]; then
    cd "$(git rev-parse --show-toplevel)"
  fi
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 https://github.com/stranske/Workflows.git "$revision"
  fi
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/issue-3820-runs.XXXXXX")
  git -c tar.umask=0022 archive --output="$recovered/evidence.tar" "$revision" -- "$directory"
  tar -xpf "$recovered/evidence.tar" -C "$recovered"
  rm "$recovered/evidence.tar"
  printf '%s\n' "$recovered/$directory"
)
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
[pagination]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/pagination-and-mode-repair.md
[capture-integration]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/capture-obligation-integration.md
[governing-plan]: https://github.com/stranske/Workflows/blob/3c84badc9c7859de9f9c97b47fe45c77200fde13/evidence/issue-3820/governing-plan-recovery-20261011.md
