# Consumer repository sync

Use this Workflows-local guide when preparing a consumer update or diagnosing a receiving PR.

Follow [Canary-Gated Fan-out](../../docs/ops/CONSUMER_REPO_MAINTENANCE.md#canary-gated-fan-out) for the Maint 68 procedure. Preview reports the proposed changes. A canary run can update only the [configured canaries](../../config/consumer_sync_canaries.json). Promotion to other receivers needs green Maint 71 evidence for the same plan. A corrected canary updates its existing candidate PR.

Inspect the five most recent runs from any checkout.

```sh
gh run list --repo stranske/Workflows --workflow maint-68-sync-consumer-repos.yml --limit 5
```

If the expected change is missing on a receiving default branch, use [Drift Detection](../../docs/ops/CONSUMER_REPO_MAINTENANCE.md#drift-detection) to find its delivery status.
