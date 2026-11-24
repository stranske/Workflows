# Positive evidence clauses preserve diagnostics and genuine run unions

These records document the Workflows #3820 verifier change and its review
follow-ups. The original index describes the native findings, the paired
red/green results and the limits of the local checks. [Original evidence index][original]

- Native finding 4289392041 has a [failing trailing-predicate case][trailing-red] and [passing result][trailing-green].
- [Native coordination failure][red] and [passing result][green]
- [Final coordination validation][validation] and [Markdown scope receipt][markdown]
- [Complete offline packet](positive-evidence-clauses.tar.gz) with all 45 original files, including the original README

From a Workflows checkout, extract into a separate directory and verify the
original paths and SHA-256 hashes. The packet needs no Git history or network
access. The captured commands and results are historical evidence.

```bash
restored=$(mktemp -d) &&
  tar -xpzf evidence/issue-3820/positive-evidence-clauses/positive-evidence-clauses.tar.gz -C "$restored" &&
  (cd "$restored" && shasum -a 256 -c SHA256SUMS) &&
  printf 'Recovered evidence under %s/evidence/issue-3820/positive-evidence-clauses\n' "$restored"
```

[original]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/README.md
[red]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/coordination-native-red.log
[green]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/coordination-green.log
[validation]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/coordination-validation.log
[markdown]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/markdown-scope-receipt.json
[trailing-red]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/trailing-negative-red.log
[trailing-green]: https://github.com/stranske/Workflows/blob/e117d4e278e07c6f418aaad355f49a6b11aa2e7d/evidence/issue-3820/positive-evidence-clauses/trailing-negative-green.log
