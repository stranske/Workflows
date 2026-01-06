# Workflow Artifact Checklist

## Before Creating or Modifying Any Workflow

**ALWAYS check if the workflow creates files that need to be in .gitignore**

### Why This Matters

Workflows that write files to the working directory can cause:
- **Merge conflicts** in consumer repos when templates sync
- **Hours of debugging** to resolve conflicts across 7+ repos
- **CI failures** from uncommitted tracked files
- **Git pollution** from auto-generated temporary files

### Quick Check Process

```bash
# 1. Search workflow for file-writing operations
grep -iE "(write|create|>>|>|tee|artifact|output)" .github/workflows/your-workflow.yml

# 2. Look for these patterns that write files:
# - Shell redirects: echo "text" > file.txt
# - Append operations: data >> log.txt
# - Python writes: open('file.txt', 'w')
# - File creation: touch, mkdir -p, cp
# - Artifact exports: actions/upload-artifact

# 3. Run the workflow and check git status
gh workflow run your-workflow.yml -f test_param=value
# Wait for completion...
git status --ignored

# 4. Check for new untracked or ignored files
git ls-files --others --exclude-standard
git ls-files --ignored --exclude-standard
```

### Common Artifact Patterns That Need .gitignore

| Pattern | Why It Should Be Ignored | Example Workflows |
|---------|-------------------------|-------------------|
| `*-status.json` | Auto-generated status tracking | Gate, autofix, keepalive |
| `*-report.json` | Workflow output reports | CI, testing, coverage |
| `*-summary.json` | Summary files for step outputs | Agent workflows |
| `codex-*.md` | Agent prompt/output files | Keepalive, agent bridge |
| `verifier-context.md` | Verification state | Autofix loop |
| `*.tmp`, `*.temp` | Temporary processing files | Any script-heavy workflow |
| `.cache/`, `tmp/` | Cache directories | Build, test, validation |
| `dist/`, `build/` | Build outputs | Package workflows |

### Workflow Types Requiring Extra Scrutiny

#### 1. Agent/LLM Workflows
```yaml
# These often create prompt/output files
- codex-prompt.md
- codex-output.md
- verifier-context.md
- agent-state-*.json
```

#### 2. Status/Report Workflows
```yaml
# These track state across runs
- autofix_report_enriched.json
- keepalive-metrics.ndjson
- ci-status-*.json
```

#### 3. Build/Artifact Workflows
```yaml
# These create build outputs
- dist/
- build/
- .artifacts/
- *.whl, *.tar.gz
```

#### 4. Test/Coverage Workflows
```yaml
# These generate test artifacts
- coverage.json
- .coverage
- htmlcov/
- test-results/
```

### Decision Tree

```
Does the workflow write files to the repo?
├─ Yes → Are they needed in git history?
│  ├─ No → Add to .gitignore ✓
│  └─ Yes → Are they auto-generated?
│     ├─ Yes → Use workflow artifacts instead, add to .gitignore ✓
│     └─ No → Ensure manual review process for commits
└─ No → Safe to proceed ✓
```

### Safe Alternatives to Writing Files

Instead of writing status/report files to the working directory:

1. **Use workflow artifacts** (don't pollute git):
   ```yaml
   - uses: actions/upload-artifact@v4
     with:
       name: report
       path: report.json
   ```

2. **Use step outputs** (for small data):
   ```yaml
   - id: status
     run: echo "result=success" >> $GITHUB_OUTPUT
   ```

3. **Use job summaries** (for readable reports):
   ```yaml
   - run: echo "## Status" >> $GITHUB_STEP_SUMMARY
   ```

4. **Use PR comments** (for visibility):
   ```yaml
   - uses: actions/github-script@v7
     with:
       script: |
         github.rest.issues.createComment({
           issue_number: context.issue.number,
           body: 'Status: Success'
         })
   ```

### Checklist for New Workflows

- [ ] Searched workflow file for file-writing operations
- [ ] Identified all files created in working directory
- [ ] Added necessary patterns to .gitignore
- [ ] Tested workflow with `git status --ignored`
- [ ] Verified no new untracked files appear
- [ ] Documented any intentional tracked files
- [ ] Considered using workflow artifacts instead
- [ ] Checked if template sync will propagate artifacts to consumer repos

### Template Workflows (Extra Critical)

Workflows in `templates/consumer-repo/.github/workflows/`:
- **Will sync to 7+ consumer repos**
- **One artifact file = 7+ repos with conflicts**
- **Must be perfect before first sync**

Before syncing templates:
```bash
# 1. Add artifacts to consumer repo template .gitignore
vim templates/consumer-repo/.gitignore

# 2. Add artifacts to main repo .gitignore
vim .gitignore

# 3. Test workflow in main repo first
gh workflow run your-workflow.yml

# 4. Verify no artifacts committed
git status --ignored

# 5. Dry-run sync to see impact
gh workflow run maint-68-sync-consumer-repos.yml -f dry_run=true

# 6. If clean, sync to consumers
gh workflow run maint-68-sync-consumer-repos.yml
```

### Recovery from Artifact Pollution

If you've already synced a workflow that creates tracked files:

```bash
# 1. Add patterns to .gitignore in Workflows repo
echo "pattern-*.json" >> .gitignore

# 2. Add to consumer repo template .gitignore
echo "pattern-*.json" >> templates/consumer-repo/.gitignore

# 3. Remove from git tracking (but keep files)
git rm --cached pattern-*.json
git commit -m "chore: untrack auto-generated artifact files"

# 4. Sync updated .gitignore to all consumer repos
gh workflow run maint-68-sync-consumer-repos.yml

# 5. In each consumer repo, remove from tracking
for repo in Travel-Plan-Permission Template trip-planner Manager-Database \
            Portable-Alpha-Extension-Model Trend_Model_Project Collab-Admin; do
  git clone "git@github.com:stranske/${repo}.git" "/tmp/${repo}"
  cd "/tmp/${repo}"
  git rm --cached pattern-*.json || true
  git commit -m "chore: untrack auto-generated artifact files" || true
  git push
  cd -
done
```

## Examples

### ✅ Good: No File Pollution
```yaml
- name: Generate report
  run: |
    python generate_report.py > report.json
    
- name: Upload report
  uses: actions/upload-artifact@v4
  with:
    name: report
    path: report.json
```

### ❌ Bad: Creates Tracked File
```yaml
- name: Generate report
  run: python generate_report.py > report.json
  
# report.json now in working directory, will be tracked!
```

### ✅ Good: Use Step Outputs
```yaml
- id: status
  run: |
    STATUS=$(python check_status.py)
    echo "result=${STATUS}" >> $GITHUB_OUTPUT
    
- name: Use status
  run: echo "${{ steps.status.outputs.result }}"
```

### ❌ Bad: Write Status File
```yaml
- run: python check_status.py > status.json
- run: cat status.json  # status.json now tracked!
```

## See Also

- [CLAUDE.md](../CLAUDE.md) - Critical debugging workflow
- [.gitignore](../.gitignore) - Current ignore patterns
- [templates/consumer-repo/.gitignore](../templates/consumer-repo/.gitignore) - Consumer repo patterns
