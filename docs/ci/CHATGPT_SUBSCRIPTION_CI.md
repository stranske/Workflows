# Codex subscription authentication in Workflows CI

If the Codex runner or auth health check reports an expired or already-used
credential, follow the [Codex token refresh procedure](../ops/CODEX_TOKEN_REFRESH.md#how-to-refresh-tokens).
It covers re-authentication, updating the affected repository's Actions secret,
and verifying a subsequent run.

The runner uses the `CODEX_AUTH_JSON` secret for subscription authentication.
The [token lifecycle](../ops/CODEX_TOKEN_REFRESH.md#token-lifecycle-overview)
describes when the runner can persist refreshed credentials and when an operator
must update the secret.

The [December 2025 authentication history](https://github.com/stranske/Workflows/blob/c998308fc1795096f4a42bcfcdd77ef53832cfd1/docs/ci/CHATGPT_SUBSCRIPTION_CI.md)
records how the original CI approach evolved.
