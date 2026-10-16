# Explicit registry bootstrap proof

Root #3898; prerequisite for draft #3921. This is a data migration preserving
existing effective agent routing, before the strict parser becomes trusted.

Executed the current production `routingLabelsFromRegistry` parser with the
unmodified trusted-base registry and then the proposed registry. Both results:

```
agent:auto, agent:claude, agent:codex, agent:copilot, agent:cursor, agent:gemini,
agents:auto-pilot, agents:keepalive
```

The only registry changes are three explicit `enabled: true` fields for Codex,
Claude and Cursor. Existing Gemini true/Aider false values remain unchanged.
An independent YAML comparison confirmed every effective enabled value matches
the prior default, every nested preflight mapping is unchanged, and source and
consumer registry bytes are identical. Adjacent receipt.json records actual
parser outputs and registry byte hashes. Full 10-test focused routing/resolver/
parser-alignment output is retained in bootstrap-green.txt.

Commands used /opt/anaconda3/bin/python3 and Node:

```
python3 -m pytest tests/workflows/test_agents_guard_fork_status_publication.py -k 'registry_backed_routing or actual_registry_resolver or registry_parser_and_receipt_pin' -q
```

No workflow/parser changes or new divergence are introduced by this precursor.
The strict-parser PR continues to read an immutable trusted base registry, and
can rebase after this migration is admitted. No native acceptance or merge is
claimed. Root #3898 stays open.
