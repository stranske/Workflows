# Astra high-reasoning execution

The owner requested GPT-6 Astra for high-reasoning work on 2026-09-04.
As of 2026-09-19, ordinary PR implementation uses `codex-default` and
`gpt-5.6-sol` at high effort. The reusable Codex worker uses the same default;
autofix callers explicitly use `gpt-5.6-terra` at medium effort. Explicit
`codex-hard` and `codex-hardest` profiles retain Astra at medium and high effort
for difficult judgment or design work. The Codex checkbox verifier remains on
Astra at medium effort because a false PASS is consequential. Codex CLI is
pinned to 0.153.2.
The active role table and dispatch contract are in [CODEX_ROLE_ROUTING.md](CODEX_ROLE_ROUTING.md).

Astra is also available as a read-only profile-trial arm. The runner remains
pinned to an immutable commit; Sol, Terra, and Luna trial identities are retained.
The auxiliary `verifier-balanced` selection remains provisional Terra, since
that is a separate balanced workload and no paired Astra benchmark is claimed.

The registry and catalog are distributed through Maint 68 and the immutable
Maint 71 promotion/delivery process. Reusable worker changes take effect through
`@main`; consumer registry changes require successful sync delivery.

Astra API clients use Responses with high reasoning and omit temperature.
Official compatibility: https://developers.openai.com/api/docs/guides/latest-model
