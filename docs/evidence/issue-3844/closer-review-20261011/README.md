# Existing PR 3846 review repair

Actual network retry attempts now share the discovery request budget; retries cannot exceed maxRequests. The evaluator crash fallback preserves missing-key ownership instead of silently removing needs-human. No permissions, token scopes or dispatch surfaces changed.

Production helper regression: original implementation exceeds the cap (RED); restored repair passes 13 Node tests. Actual workflow shell crash fallback fails both ownership assertions before repair (RED), then all 26 health evaluator/workflow tests pass. Raw logs alongside this receipt.

The request to mark every HTTP 401/403 as human-owned is not adopted: rejected credentials can require automation-owned credential/runner repair. This contract requires fresh evidence of an external access action before assigning a human blocker. Missing configured cloud keys retain the existing escalation behavior; rejected configured keys retain their degraded diagnostic and automation recovery ownership.
