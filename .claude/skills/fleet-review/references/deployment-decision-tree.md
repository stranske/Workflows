# Deployment decision-tree walkthrough (the "shoulder tap")

Run this interactively, **one app at a time, with the user**, when a repo first
becomes testable, before sharing a tool with a colleague, when adding/enabling an
LLM feature, or when onboarding someone. Ask the gating questions, pick the path,
and record the chosen path for that app. Written to be usable by a non-programmer.

## The one rule: two separate boundaries

- **Network boundary** — proprietary/internal data must not leave the org or be stored outside it.
- **LLM boundary** — proprietary data must not go to an LLM without specific authorization.

The org has **no objection to ordinary programs processing data**. So keep both
boundaries explicit and isolated: a tool's deterministic math can run on real data
freely; only the "leaves the building" and "talks to an LLM" parts are restricted.

## The five privacy-safe options (the toolkit)

1. **Client-side WebAssembly** — `stlite` (Streamlit-in-browser), `Pyodide`, `JupyterLite`. App runs entirely in the work browser tab: no install, no terminal, no server, data never leaves the machine, no LLM in this path. **Default best option now — needs nothing from the tech team.**
2. **In-perimeter browser hosting** — Power Apps/Power BI (M365), an internal server / Azure web app, or Streamlit-in-Snowflake. Browser-reachable, data stays inside. *Needs IT.* **Future** (M365 + internal server flagged worth tracking).
3. **Isolate the LLM boundary** — split each tool into a deterministic core (runs on real data) and LLM features behind a switch (redact-first, or disabled, until an authorized endpoint exists).
4. **Two-track: synthetic for show, real for work** — demo to colleagues on a public host using *fake* fixture data; do real runs only via Option 1 or 2.
5. **Authorized no-train LLM endpoint** (e.g. Azure OpenAI in-tenant) — *future*; depends on tech-team progress.

Only Streamlit Cloud / Cloudflare Pages / an existing deployed URL / viewable CI
artifacts need **nothing but a browser**. GitHub Codespaces is the universal
*dev* fallback (a terminal in a browser tab) — external cloud, so synthetic /
non-proprietary data only.

## The decision tree — ask these per app

1. **Does this app need REAL internal data to do its job?**
   - **No** → it's *public-safe*. Use a public browser path (GitHub Codespaces, or a deployed demo). Easiest; great for adoption demos. **Done.**
   - **Yes** → go to 2.
2. **For testing/demos, can you use synthetic/fixture data instead of real?**
   - **Yes** → demo on a public path with synthetic data (Option 4); do real runs via step 3.
   - **No** → go to 3.
3. **Does the task need LLM features, or just computation?**
   - **Just computation** → **Option 1 (stlite/WASM)** — runs in the work browser, nothing leaves. Best now.
   - **Needs an LLM on proprietary data** → no authorized endpoint yet → **Option 3**: disable/redact the LLM part for now; revisit when Option 5 lands.

## When to tap on the shoulder (trigger this walkthrough)

- When a repo first becomes **testable** (has a usable entry point).
- **Before** deploying or sharing a tool with a colleague.
- When **adding or enabling an LLM feature**.
- When **onboarding** someone to a tool.

## Per-app starting recommendations (confirm the bold gate live)

| App | Needs real internal data? | Recommended path now |
|---|---|---|
| **trip-planner** | **No** (confirmed) | Public — Codespaces or a deployed demo. Best first adoption demo. |
| **Pension-Data** | Public filings — likely **No** (confirm) | Public path; internal only if joined to private data. |
| **Trend_Model_Project** | **Yes** (return data) | Option 1 (stlite) for real runs; synthetic demo for show. |
| **Portable-Alpha-Extension-Model** | **Yes** | Option 1 (stlite); synthetic demo. |
| **Counter_Risk** | **Yes** | Option 1 (stlite) after the console-script fix; synthetic demo. |
| **Manager-Database** | **Yes** + LLM | Deterministic/search core → Option 2 (later) or stlite; LLM features Option 3 (off/redacted) now; synthetic demo now. |
| **Inv-Man-Intake** | **Yes** + LLM | Deterministic parsing via WASM/local; LLM gated (Option 3). |
| **learning-management-system** | **Yes** (already does local-first redaction) | Option 1/3; its redaction path is the template. |
| **Travel-Plan-Permission** | **Confirm** (may hold personnel data) | Default to internal/Option 1 until confirmed. |
| **Workflows** | N/A (dev infrastructure) | Observe in the browser via GitHub; not a data app. |

Adopt **Streamlit as the house UI pattern**; don't rewrite to React. Treat "no
live URL" as a release blocker — ship a browser-reachable instance the moment a
tool is usable, and verify it live in-session (never "the next cron tick will confirm").

## Cross-location consistency (work PC web Claude Code ↔ Mac at home)

Local skills/automations/memory live in `~/.claude` / `~/.codex`, which web Claude
Code on the work PC can't see. To make capability travel:

1. **Put shared skills *inside a repo*** (committed `.claude/skills/`) — they travel to web Claude Code when the repo is opened. (This skill is built that way on purpose.)
2. Keep key knowledge in committed files (`CLAUDE.md`, `docs/`), not only local memory.
3. Commit shared settings/permissions to `.claude/settings.json`.
4. **GitHub Codespaces** gives an identical browser dev environment anywhere (synthetic data only).
5. (Bigger move) Migrate the local-cron opener/closer/handoff automations to cloud-scheduled remote agents or GitHub Actions so they run regardless of which machine is on. Flag for later.

Bottom line: shift capability out of the Mac's home folder into **the repo (git)**
and **the cloud (Codespaces / scheduled remote agents)**.
