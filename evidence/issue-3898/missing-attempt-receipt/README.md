# Missing attempt receipt replaces stale success

Native finding 4289154448 on original final head e4b92aa996ef1421d6f1a92fc0e5c08f06e6ea71 reported that missing or ambiguous evaluated-policy step metadata threw before replacing stale same-head success. The existing unit test incorrectly expected this no-write outcome.

Six production-path fixture cases now fail on the original publisher: missing receipt with no status, and stale same-head success with absent, malformed, failed, incomplete or duplicate receipt metadata. The original RED log is retained unchanged. The failure is an absent publication result because the original function throws.

The repaired publisher catches only receipt-validation failure after all existing immutable head/base/attempt checks and publishes the required failure. A policy digest mismatch retains its existing failure path. A valid direct verdict remains authoritative. Source and consumer helper bytes match.

Full focused guard suite: 566 passed. New controls retain denial of status writes and head/attempt drift. The old immutable receipt contains a published status id, not a duplicated state field; assertions bind that id and the actual failure-status POST.

Commands: `/opt/anaconda3/bin/python3 -m pytest tests/workflows/test_agents_guard.py tests/workflows/test_agents_guard_publication.py tests/workflows/test_agents_guard_fork_status_publication.py -q -o addopts=`. Template sync, template drift and focused Ruff/diff checks pass.

These are local source controls, not native review acceptance, current-head hosted CI, source rollout or provider PASS.
