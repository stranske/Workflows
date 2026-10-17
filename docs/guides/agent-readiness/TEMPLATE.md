# Readiness evaluation: `<agent>` (CLI version `<x.y.z>`, evaluated `<YYYY-MM-DD>`)

**Verdict:** Ready | Ready for local use only | Not ready
**Hosted CI verdict / local verdict:** `<one line each>`

## 1. What it is

One paragraph: the vendor, the CLI binary and how it relates to any predecessor.

## 2. Stage 0 questions

Evidence class for each cell: P production use, R real trial, F fixture check, W wiring/documentation.
`unknown — would need <probe>` is a valid answer.

| # | Question | Blocker? | Hosted CI | Local | Evidence | Notes / probe |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Unattended authentication on a clean Linux runner with a repo-secret credential | **Yes** | | | | |
| 2 | What the credential bills; acceptable for unattended use | **Yes** | | | | |
| 3 | Headless print mode: bounded runtime, machine-readable output, non-zero exit on failure | **Yes** | | | | |
| 4 | Sandbox: available, usable on a Linux runner, or confinable by the runner | **Yes** | | | | |
| 5 | Reliability: stalls, silent success without work, empty output | **Yes** if reproducible | | | | |
| 6 | Commits on its own; commit identity | No | | | | |
| 7 | Model selector stability; fails loudly on an unknown model | No | | | | |
| 8 | Capacity model readable without spending | No | | | | |
| 9 | Documented position on unattended or automated use | Record | | | | |
| 10 | Install on Linux: method, integrity verification, libc requirements, version pinning | No | | | | |

## 3. History of defects seen (this repository and upstream changelog)

| When | Symptom | Class (false success / hang / auth / isolation / other) | Fixed upstream? |
| --- | --- | --- | --- |

## 4. Limitations and how to re-test them

| Limitation | Affects | What evidence would clear it | Cheapest probe |
| --- | --- | --- | --- |

## 5. Re-evaluation triggers

List concrete events (a new CLI major version, a documented credential type, a changelog line)
that should prompt re-running section 2.

## 6. Recommendation

What may be done now (for example local use), what must not, and the first stage of the
[add-an-agent ladder](../ADD_NEW_AGENT.md) to attempt once the blockers clear.
