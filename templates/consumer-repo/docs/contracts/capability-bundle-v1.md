# Capability Bundle v1

`capability-bundle/v1` is the neutral Workflows contract for portable, deterministic keepalive capability fragments. A bundle may carry task and acceptance fragments plus gate/playbook references, but it must not carry local posterior weights, credentials, raw prompts, or autonomous local-control commands.

Required fields:

- `capability_id`, `version`, and `content_hash`
- deterministic `selector` predicates such as repo, agent, mode, and labels
- `owner`, `fragments`, `gates`, and `rollback`
- optional `expires_at` and `playbooks`

The content hash is `sha256:` over the canonical JSON payload excluding `content_hash`. Keepalive prompt composition reports applied bundle IDs/hashes and rejected reasons; keepalive metrics record the same evidence so downstream dashboards can distinguish "no bundle matched" from "bundle applied."
