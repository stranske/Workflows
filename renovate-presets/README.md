# Fleet Renovate preset

See the [Fleet Renovate intake policy](../docs/ops/CONSUMER_REPO_MAINTENANCE.md#fleet-renovate-intake-policy)
for schedules, limits, grouping, and exceptions.

The [fleet preset](fleet.json) extends the [generated consumer managed-path preset](consumer-managed-paths.json).

## Validate local configuration

From the repository root, use Node.js 24.11.0 or a later 24.x release to validate
the Workflows config, both presets, and the create-only consumer config:

```bash
npx --yes --package renovate@43.285.3 -- renovate-config-validator --no-global \
  renovate.json renovate-presets/fleet.json renovate-presets/consumer-managed-paths.json \
  templates/consumer-repo/.github/renovate.json
```

This checks the four local files. Verify published GitHub preset references
separately to confirm that the top-level `extends` targets are available.
