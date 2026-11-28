# Historical operator source records

These records preserve earlier rollout plans, audits, and verification. Use the
linked implementation or guide for current procedures.

| Original record | Current owner or procedure |
| --- | --- |
| [Rate-limit remediation plan](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/fixes/RATE_LIMIT_REMEDIATION_PLAN.md) | [API rate-limit management](../ops/api-rate-limit-management.md) |
| [Local multi-agent orchestrator design](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/plans/local-multi-agent-orchestrator.md) | [Orchestrator architecture](https://github.com/stranske/Orchestrator/blob/main/ARCHITECTURE.md) and [Workflows local lanes](../ops/LOCAL_LANES.md) |
| [Phase 5D delegation design](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/plans/phase-5d-delegation-policy.md) | [delegation policy entry point](../plans/phase-5d-delegation-policy.md) |
| [Provider-agnostic coding agents plan](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/plans/provider-agnostic-coding-agents.md) | [agent infrastructure references](../plans/provider-agnostic-coding-agents.md) |
| [Workflows documentation drift audit](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/reports/doc-drift-audit/stranske__Workflows-doc-drift.md) | [drift checker](../../scripts/check_docs_drift.py) |
| [LLM metadata call-site inventory](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/reverification/llm-config-metadata-call-sites.md) | [PR verifier](../../scripts/langchain/pr_verifier.py) and [follow-up generator](../../scripts/langchain/followup_issue_generator.py) |
| [#3683 priority-label color verification](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/verification/issue-3683-priority-color-drift.md) | [label contract](../../.github/labels-core.yml) and [bootstrap label regression](../../tests/scripts/test_bootstrap_consumer_labels.py) |

From a Workflows clone, recover the complete records with their original paths
and file modes:

```sh
(
  set -e
  cd "$(git rev-parse --show-toplevel)"
  revision=c998308fc1795096f4a42bcfcdd77ef53832cfd1
  if ! git cat-file -e "$revision^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 origin "$revision"
  fi
  recovered=$(mktemp -d "${TMPDIR:-/tmp}/workflow-source-history.XXXXXX")
  git -c tar.umask=0022 archive -o "$recovered/source.tar" "$revision" \
    docs/fixes/RATE_LIMIT_REMEDIATION_PLAN.md \
    docs/plans/local-multi-agent-orchestrator.md \
    docs/plans/phase-5d-delegation-policy.md \
    docs/plans/provider-agnostic-coding-agents.md \
    docs/reports/doc-drift-audit/stranske__Workflows-doc-drift.md \
    docs/reverification/llm-config-metadata-call-sites.md \
    docs/verification/issue-3683-priority-color-drift.md
  tar -xpf "$recovered/source.tar" -C "$recovered"
  rm "$recovered/source.tar"
  printf '%s\n' "$recovered"
)
```
