# Shared Design System

Two themes on one token foundation, plus an orthogonal density axis.

- **`theme-air`** (Ink & Air) — default; work / outward-facing tools.
- **`theme-paper`** (Warm Paper) — friendlier apps (Reader, LMS).
- **`density-compact`** — tightens spacing for data-dense screens (e.g. Trend tables) **without** changing the theme.

## Use

```html
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="components.css">

<body class="theme-air">            <!-- or theme-paper; add density-compact for dense screens -->
  <div class="ds">
    ...components (.panel, .kpi, .appbar, table, .btns, .callout, ...)...
  </div>
</body>
```

- Components are scoped under `.ds` so they never leak into a host app's styles.
- `components.css` is theme-agnostic — it only reads tokens. Don't fork it.

## Per-app customization

Override any token in an app stylesheet loaded **after** `tokens.css`:

```css
.theme-air { --accent: #0f6f6a; }   /* this app wants a teal accent */
```

That's the "default with per-app customization" model: the base is canonical; an app changes only the tokens it needs.

## Files

| File | Role |
|---|---|
| `tokens.css` | Variables — themes + density. **Source of truth for the look.** |
| `components.css` | Component styles, token-driven and theme-agnostic. |
| `ds_streamlit.py` | Streamlit-native helpers for the same presentation patterns. |

## Theme → app mapping (proposed)

- **Ink & Air:** Trend_Model_Project, Counter_Risk, Manager-Database, Inv-Man-Intake, Pension-Data, Portable-Alpha-Extension-Model, trip-planner, Travel-Plan-Permission. Use `density-compact` on Trend/Counter_Risk data-dense screens.
- **Warm Paper:** Reader, learning-management-system.

## Status & next step

This kit is managed from `Workflows/templates/consumer-repo/design-system/` and distributed by the Maint 68 Sync Consumer Repos GitHub Actions workflow through `.github/sync-manifest.yml`. Update it here first, then let the sync workflow replace consumer copies.
