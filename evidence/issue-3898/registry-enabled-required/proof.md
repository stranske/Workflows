# Required agent enabled flag: causal proof

Root: stranske/Workflows#3898. Base: a09890634bf24c44a021d75b6aa484a31e5fb54a.

Before repair, `agents.set(key, true)` silently admitted an agent without its own
`enabled` field. The new 160-case matrix executed all eight production parser
copies and produced **40 failed / 120 passed** on the unchanged source. Missing
flags at EOF, agent/section transitions, and nested-only flags were accepted.
`registry-enabled-red.log` is the full authentic RED output.

The repair finalizes each entry before a new agent, top-level section, repeated
agents mapping, and EOF; no missing flag can reach a routing-label result.
Exactly one canonical agent-level boolean is required. Existing duplicate/value
rejection remains intact. Nested preflight flags cannot supply or override it.
All eight parser bodies must be byte-identical, and both registry files match.

The initial broad run exposed the shipped Codex/Claude/Cursor entries missing
agent-level flags (47 failures / 695 passes). Both registries now explicitly
retain their previous effective true values; Gemini remains true, Aider false.
Nested preflight values are unchanged. This failing migration run is retained
in the automation evidence directory, not disguised as a final validation.

The final four-file guard regression after native review repair passed **798 tests**, including direct/fork
publisher failure writes and stale head/attempt suppression. Additional final
parser-byte parity proof is retained separately. Full GREEN and validation logs
are adjacent text files; receipt.json binds their SHA256 digests.

Native review found a stale direct corrective-write path. Its actual source/
template matrix produced 26 RED failures before repair. Current PR head/base/
repository/ref, run/attempt, latest inventory and final bindings now gate the
write. The 52-case both-event matrix plus adjacent cases passes; full final
regression is 798 passed. Pull-request Actions run heads bind to PR head rather
than the synthetic merge SHA. Actions read is the only permission addition.
`registry-enabled-direct-binding-red.log` and `registry-enabled-reviewed-final-*`
retain this review repair proof, including Black and Health74 drift validation.
A registry-only precursor (#3922) admits unchanged effective routing before this
strict parser can consume those immutable trusted-base registry facts.

Commands (runtime /opt/anaconda3/bin/python3):

```
python3 -m pytest tests/workflows/test_agents_guard_registry_enabled.py tests/workflows/test_agents_guard_fork_status_publication.py tests/workflows/test_agents_guard_publication.py tests/workflows/test_agents_guard.py -q
python3 scripts/validate_template_sync.py
python3 scripts/validate_template_completeness.py --strict
python3 -m ruff check tests/workflows/test_agents_guard_registry_enabled.py tests/workflows/test_agents_guard_publication.py tests/workflows/test_agents_guard_fork_status_publication.py
node --check .github/scripts/agents-guard-fork-status-publication.js
git diff --check
```

Local proof does not establish hosted CI, provider acceptance, merge or rollout.
No denied reproduction/assessment operation was retried. The existing root issue
remains open pending native source acceptance and the parent's guarded delivery.
