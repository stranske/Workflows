# Presentation Patterns — the fleet design-system rollout standard

The cross-repo UX-Review baseline (2026-06-22, 8 apps) found that **every app's engine works; the
failures are presentation + deployment.** Deployment is a separate program. This doc covers the
**presentation** class: it collapses the ~12 recurring presentation findings into **6 reusable
patterns**, each with a rule, a design-system component (`components.css` / `tokens.css`), a
per-app-type application (Streamlit / web-SPA / static-PWA), and the fleet findings it closes.

**Principle:** apps should consume a *pattern*, not invent a bespoke fix. One pattern, applied
everywhere, beats N one-off PRs — and it's why this is a design-system rollout, not a bug list.

---

## The 6 patterns

### P1 — Light, understated theme by default

**Rule:** never ship a default dark theme; default to `theme-air` (Ink & Air). Dark is opt-in only.
- **web:** load `tokens.css` + `components.css`; root element `class="ds theme-air"` (`theme-paper` for friendlier apps).
- **Streamlit:** `.streamlit/config.toml` `[theme] base="light"` + the shared `ds_streamlit.inject_theme()` (maps the `theme-air` tokens to Streamlit's theme). *Already prototyped for TMP.*
- **Fixes:** default-dark on Trend_Model_Project / Portable-Alpha / Manager-Database / Inv-Man-Intake.

### P2 — Empty state = title + reason + next action

**Rule:** a "no data yet" surface ALWAYS shows a title, a one-line reason, and a **next-action CTA**.
NEVER a bare prompt sitting above already-rendered content, and NEVER an internal filename/path.
- **web:** `.ds .empty-state` (`.es-icon/.es-title/.es-desc/.es-cta`).
- **Streamlit:** `ds_streamlit.empty_state(title, desc, cta_label=cta_label, on_click=on_click)`.
- **Fixes:** TMP #5628 (Run-analysis CTA above results), PA #2021 (Results "Outputs.xlsx not found"),
  Manager-Database #1214 (empty default date / "Recent Activity"), LMS #351 (root `/` JSON 404).

### P3 — Errors are human messages + remediation

**Rule:** NEVER surface a raw exception, pydantic/validation dump, internal field name, or stack to a
user. Translate at the boundary to a plain message + a recovery action.
- **web:** `.ds .notice--error` (`.ic` + `.body strong` headline + `.body .act` remediation).
- **Streamlit:** `ds_streamlit.error(message, remediation)` backed by `translate_error(exc)` (maps
  known fields, e.g. `financing_mode` → "Financing mode is required").
- **Fixes:** PA #2021 (raw `ModelConfig financing_mode` / margin pydantic errors), Inv-Man-Intake (item_id),
  the broad "raw error" class across the fleet.

### P4 — Dev/diagnostic notices go to logs, not the UI

**Rule:** auth-bypass / trace-sink / observability / "dev mode" notices NEVER render in the main
content. Use logging, or at most a collapsed "Diagnostics" expander.
- **web:** n/a in the main flow; use a `<details>`/debug panel.
- **Streamlit:** `ds_streamlit.dev_note(msg)` → `logging` (not `st.warning`/`st.write`); diagnostics behind `st.expander("Diagnostics")`.
- **Fixes:** Manager-Database #1215 (auth-bypass `st.warning`), Inv-Man-Intake #630 (trace-sink banner).

### P5 — Feature-availability markers (no silent dead-ends)

**Rule:** a tab/control that isn't applicable in the current mode states so up front (a badge/label),
rather than opening into a silent empty/disabled surface.
- **web:** `.ds .badge` on the tab/control (e.g. "multi-period only", "needs setup").
- **Streamlit:** `ds_streamlit.availability_badge(label)` in the tab title / disabled control caption; use `plain=False` only in trusted HTML containers.
- **Fixes:** TMP #5629 (4/6 Results tabs empty — fixed by labelling, the canonical example), PA #2026
  (upload-only pages with no sample path → mark/offer the sample).

### P6 — No raw internal identifiers in user surfaces

**Rule:** decode internal IDs / fixture filenames / record keys into human-readable labels before display.
- **web/Streamlit:** a display-name mapping; keep the raw id as secondary/`title=` metadata if useful.
- **Fixes:** Inv-Man-Intake #629 (opaque `item_id`), #630 (raw fixture filename in selector), PA Results (`Outputs.xlsx`).

---

## Finding → pattern map (presentation class)

| Finding | Pattern(s) |
|---|---|
| TMP #5628 empty-state CTA above results | P2 |
| TMP #5629 unmarked empty tabs *(fixed)* | P5 |
| Manager-Database #1214 empty default views | P2 |
| Manager-Database #1215 auth notice in UI | P4 |
| Inv-Man-Intake #629 non-actionable raw-JSON queue | P6 (+ a real action, app-specific) |
| Inv-Man-Intake #630 trace-sink + raw filenames | P4, P6 |
| Portable-Alpha #2021 raw errors / empty states | P2, P3 |
| Portable-Alpha #2026 upload-only, no sample | P5 |
| Pension-Data #594 *(deployment program — offline)* | — |
| LMS #351 root JSON 404 / empty surfaces | P2 (+ deployment) |
| Default dark theme (TMP/PA/MD/IMI) | P1 |

## Streamlit design kit (most of the fleet is Streamlit)

For Streamlit apps, use the [shared Python helpers](ds_streamlit.py) installed alongside the web stylesheets.
- `inject_theme()` — applies the `theme-air` palette (P1); pairs with `.streamlit/config.toml`.
- `empty_state(title, desc, cta_label=cta_label, on_click=on_click)` (P2)
- `notice(kind, title, body, action=None)` and `error(message, remediation=None)` + `translate_error(exc)` (P3)
- `dev_note(msg)` → logging; `diagnostics_expander()` (P4)
- `availability_badge(label)` (P5)
- `humanize_id(raw, mapping)` (P6)

## Use the installed kit

Maint 68 distributes the kit to each managed consumer’s `design-system/` directory. See the [installation and styling guide](README.md) for file roles and stylesheet order. Make shared changes in the Workflows template so the next sync delivers them.

For an app change, select the pattern that matches the finding, apply it on the affected screen and exercise that screen with the input that exposed the finding. The finding map above records the June review that introduced the patterns.

_Authored 2026-06-22 from the UX-Review fleet baseline. Components live in `components.css`/`tokens.css`
(this dir); see each repo's `docs/ux-review/REVIEW_LOG.md` for its findings + scores._
