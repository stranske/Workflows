# Capacity-profile documentation correction

Finding: Workflows#3821 discussion_r4238376324 on 6a4a5a13e7711bf51701fe06d86708a95902277c.

Adopted the review: hosted langchain-openai 1.4.1 supplies Terra profile facts. Profile availability varies by SDK version and is distinct from native message-counter availability. The configured Chat Completions adapter's absent native counter still leaves expanded provider capacity UNKNOWN. No live provider acceptance is asserted.

Deliberate RED: the new documentation regression failed against the original contract (1 failed, 0.70s). After correcting the contract, the evidence-profile and recovery suites passed with the authenticated comparison capture (98 passed, 13.14s). Ruff, Black and git diff --check passed. This is a documentation/fixture regression result, not a provider verdict or full hosted CI result.
