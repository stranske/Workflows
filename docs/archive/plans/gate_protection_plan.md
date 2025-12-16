# Gate Workflow Branch Protection Plan

## Scope and Key Constraints
- Enforce the default-branch protection rule so it always requires **Gate / gate** and **Health 45 Agents Guard / Enforce agents workflow protections**.
- Remove any legacy required status checks that overlap or conflict with the Gate or Health 45 Agents Guard protections (e.g., older `CI` workflows).
- Enable the "Require branches to be up to date" option so merges must include the latest default-branch commits.
- Preserve existing job names inside `gate.yml` (`python ci`, `docker smoke`, `gate`) so downstream automation retains stable identifiers across the Python matrix and aggregation steps.
- Communicate the new requirement in contributor-facing docs (CONTRIBUTING.md) without altering unrelated guidance.

## Acceptance Criteria / Definition of Done
- Default branch protection rule lists exactly the two contexts above and prevents merging until they succeed.
- Any deprecated required checks (e.g., `CI`) are removed from the protection rule unless explicitly preserved with `--no-clean` for auditing.
- "Require branches to be up to date" is enabled for the default branch protection rule.
- CONTRIBUTING.md explicitly instructs contributors that the Gate and Health 45 Agents Guard checks must pass before merging.
- A test pull request shows the Gate and Health 45 Agents Guard checks as required and blocks merge when failing or pending.

## Initial Task Checklist
1. Audit current branch protection settings for the default branch and note existing required checks.
2. Update branch protection:
  - Add or confirm the required contexts: **Gate / gate** and **Health 45 Agents Guard / Enforce agents workflow protections**.
   - Remove obsolete required checks unless explicitly retained for audits.
   - Enable "Require branches to be up to date" if not already set.
3. Verify recent `gate` and Health 45 Agents Guard workflow runs to confirm job naming and stability.
4. Create or update documentation (CONTRIBUTING.md) to mention the required Gate and Health 45 Agents Guard checks.
5. Open a validation pull request to confirm the Gate and Health 45 Agents Guard contexts appear as required and block merge until passing.
6. Record findings and screenshots/logs (if applicable) demonstrating the protection rule and validation PR behavior.

## Implementation Summary

- Added `tools/enforce_gate_branch_protection.py` to interrogate and update the default branch protection rule via the GitHub
  REST API so the **Gate / gate** and **Health 45 Agents Guard / Enforce agents workflow protections** contexts remain required while
  "Require branches to be up to date" stays enabled. The helper accepts
  explicit `--token` and `--api-url` overrides for GitHub Enterprise Server environments while continuing to respect
  `GITHUB_TOKEN`, `GH_TOKEN`, and `GITHUB_API_URL` when flags are omitted.
- The helper defaults to `GITHUB_REPOSITORY`/`DEFAULT_BRANCH` and can run in dry-run mode to audit the current contexts before
  applying changes.
- Maintainers can add `--snapshot <path>` to the helper to emit a JSON evidence bundle that records the current, desired, and
  post-enforcement status checks for audit trails.
- Contributors without direct settings access can now request an owner to run the script with a fine-grained `GITHUB_TOKEN`
  instead of navigating the UI, ensuring infrastructure as code parity for the protection rule.
- Scheduled automation (`.github/workflows/health-44-gate-branch-protection.yml`) executes the helper nightly and on-demand,
  applying fixes whenever the optional `BRANCH_PROTECTION_TOKEN` secret is configured and always re-validating with `--check`
  using the workflow's default token so misconfigurations fail fast. When no enforcement token is provided, the verification
  step inspects the branch metadata API (which only requires repository read access) to confirm that both contexts remain
  required.

## Automation Requirements

- Create a fine-grained PAT with the **Administration: Branches** scope (repo → settings → developer settings → fine-grained
  personal access tokens). Attach it to the repository as the `BRANCH_PROTECTION_TOKEN` secret so the enforcement workflow can
  manage branch protection.
- The workflow runs on a nightly cron and via the `workflow_dispatch` trigger. When the secret is absent the enforcement step is
  skipped, but the subsequent verification still fails if any Gate or Health 45 Agents Guard context is missing so owners receive immediate alerts.
- Manual runs surface the audit diff in the workflow logs, mirroring the script's dry-run output before applying updates, and the
  resulting JSON snapshots are uploaded as workflow artifacts for long-term evidence.

## Usage Notes

Run a dry check to review the current branch protection rule (either export
`GITHUB_TOKEN`/`GH_TOKEN` or pass `--token` explicitly):

```bash
python tools/enforce_gate_branch_protection.py \
  --repo stranske/Trend_Model_Project \
  --branch main \
  --token ghp_xxx \
  --snapshot docs/evidence/gate-branch-protection/status.json
```

Expected dry-run output when the rule is correct:

```
Repository: stranske/Trend_Model_Project
Branch:     main
Current contexts: Gate / gate, Health 45 Agents Guard / Enforce agents workflow protections
Desired contexts: Gate / gate, Health 45 Agents Guard / Enforce agents workflow protections
Current 'require up to date': True
Desired 'require up to date': True
No changes required.
```

Apply corrections (if the dry run indicates drift):

```bash
python tools/enforce_gate_branch_protection.py \
  --repo stranske/Trend_Model_Project \
  --branch main \
  --token ghp_xxx --apply \
  --snapshot docs/evidence/gate-branch-protection/post-apply.json
```

The script patches `required_status_checks` in-place and leaves other branch protection toggles untouched. Use `--context` to
temporarily allow additional contexts or `--no-clean` to preserve existing extras while asserting the Gate and Health 45 Agents Guard protections.

For GitHub Enterprise Server instances, add `--api-url https://hostname/api/v3` to point the helper at the correct API root.

## Validation Checklist

- After enforcing the rule, run `gh api repos/stranske/Trend_Model_Project/branches/main/protection/required_status_checks` to
  confirm the payload lists the two contexts above and has `"strict": true`.
- Open a throwaway pull request from an outdated branch to confirm the merge box displays each required context (Gate and Health 45 Agents Guard) and blocks merges until the workflows finish successfully.
- Capture screenshots or console transcripts for the repository automation log (attach to the issue or link in meeting notes).
- Include the Health 44 step summary in the evidence bundle. The summary must display the enforcement and verification snapshots
  with the Gate and Health 45 Agents Guard contexts clearly marked as the "Before" and "After/Target" states, note that cleanup was
  disabled (`--no-clean`), and list any contexts that were added or removed during enforcement.
