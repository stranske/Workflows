# Fleet Renovate preset

`fleet.json` is the single source of truth for Renovate intake across Workflows and
the registered consumer repositories. It opens routine dependency work only in the
Monday 01:00–05:00 America/Chicago maintenance window, permits at most three routine
branches and PRs, and limits commits to two per hour.

Routine releases must be at least three days old and wait until their update-branch
checks are not pending. Vulnerability alerts bypass the window, release-age delay,
and update-branch check gate so security remediation is never held by the routine
budget.

Trusted GitHub Actions digest, pin, minor, and patch updates share one green-automerge
lane. Major updates remain visible in the Dependency Dashboard and create a PR only
after an explicit dashboard approval. Lock-file maintenance is a separate, grouped
weekly lane in the same window.

Validate the repository config before review:

```bash
npx --yes --package renovate@43.285.3 -- renovate-config-validator --no-global \
  renovate.json renovate-presets/fleet.json \
  templates/consumer-repo/.github/renovate.json
```
