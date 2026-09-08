# Astra high-reasoning execution

The owner requested GPT-6 Astra for high-reasoning work on 2026-09-04.
`codex-default`, the reusable Codex worker and checkbox verifier request
`gpt-6-astra`. Codex CLI is pinned to 0.153.2, matching the working local
installation. Explicit fast profiles and fallback identities remain independent.

Astra is also available as a read-only profile-trial arm. The runner remains
pinned to an immutable commit; old Sol trial identities are retained.
The auxiliary `verifier-balanced` selection remains provisional Terra, since
that is a separate balanced workload and no paired Astra benchmark is claimed.

The registry and catalog are distributed through Maint 68 and the immutable
Maint 71 promotion/delivery process. Reusable worker changes take effect through
`@main`; consumer registry changes require successful sync delivery.

Astra API clients use Responses with high reasoning and omit temperature.
Official compatibility: https://developers.openai.com/api/docs/guides/latest-model
