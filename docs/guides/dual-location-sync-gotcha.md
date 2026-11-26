# Changing a file with a root and consumer copy

Use the [manifest compiler](../ops/CONSUMER_REPO_MAINTENANCE.md#manifest-schema-and-compiler) to identify the file that Maint 68 will deliver. In the compiled plan, find the destination in `entries[].target` and edit its `resolved_source`.

For example, the plan takes `.github/scripts/keepalive_state.js` from the repository root. Its copy in `templates/consumer-repo/` also serves projects following the [manual script installation instructions](../../templates/consumer-repo/README.md#required-scripts-for-consumer-repos). Keep the two implementations consistent. For `.github/codex/prompts/fix_merge_conflicts.md`, the plan takes the template copy.

Follow the [distribution checklist](../STRUCTURE.md#change-a-file-distributed-to-consumers) to check paired files, review the canary diff and verify the result on the receiving default branch.
