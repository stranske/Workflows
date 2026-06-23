"""ds_streamlit — Streamlit adapter for the shared design system.

The CSS design system (tokens.css / components.css) covers the web apps. The
Streamlit Tier-A apps can't consume CSS components directly, so this module
ships the same PRESENTATION PATTERNS as small Streamlit helpers. Apps should
call these instead of inventing bespoke empty-states / error displays / dev
banners. See PRESENTATION_PATTERNS.md for the rule behind each (P1..P6).

Usage:
    from ds_streamlit import inject_theme, empty_state, error, dev_note
    inject_theme()                      # P1 — once, near st.set_page_config
    ...
    if result is None:
        empty_state("No results yet",   # P2
                    "Run the demo to generate diagnostics.",
                    cta_label="Run demo", on_click=run_demo)
        st.stop()
    ...
    try:
        cfg = build_config(...)
    except Exception as exc:
        error(*translate_error(exc))    # P3 — never show the raw exception
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from html import escape
from typing import Any

logger = logging.getLogger("ds")

# Ink & Air (theme-air) palette — keep in sync with tokens.css .theme-air.
_INK = "#0a0a0a"
_MUTED = "#737373"
_ACCENT = "#4f46e5"
_BORDER = "#ececec"
_NEG = "#dc2626"
_NEG_WEAK = "#fef2f2"
_WARN = "#b45309"
_WARN_WEAK = "#fffbeb"
_INFO_WEAK = "#f4f3ff"
_POS = "#047857"
_POS_WEAK = "#ecfdf5"

_NOTICE_STYLE = {
    "error": (_NEG, _NEG_WEAK, "✕"),
    "warn": (_WARN, _WARN_WEAK, "!"),
    "info": (_ACCENT, _INFO_WEAK, "i"),
    "ok": (_POS, _POS_WEAK, "✓"),
}


def inject_theme() -> None:
    """P1 — apply the light/understated theme. Pair with .streamlit/config.toml
    ([theme] base=\"light\"); this nudges spacing/headings to match the system."""
    import streamlit as st

    st.markdown(
        f"""<style>
        .block-container {{ padding-top: 2.2rem; max-width: 980px; }}
        h1, h2, h3 {{ letter-spacing:-.01em; }}
        .ds-badge {{ display:inline-block; font-size:.72rem; font-weight:600;
            padding:1px 7px; border-radius:999px; background:#fafafa; color:{_MUTED};
            border:1px solid {_BORDER}; vertical-align:middle; margin-left:6px; }}
        .ds-notice {{ display:flex; gap:10px; padding:11px 13px; border-radius:10px;
            font-size:.9rem; border:1px solid {_BORDER}; margin:8px 0; }}
        .ds-notice .ic {{ font-weight:700; }}
        .ds-empty {{ text-align:center; border:1px dashed {_BORDER}; border-radius:10px;
            padding:26px 20px; }}
        .ds-empty .t {{ font-weight:700; font-size:1.05rem; margin:6px 0 4px; }}
        .ds-empty .d {{ color:{_MUTED}; font-size:.9rem; max-width:42ch; margin:0 auto 12px; }}
        </style>""",
        unsafe_allow_html=True,
    )


def empty_state(
    title: str,
    desc: str = "",
    *,
    icon: str = "📭",
    cta_label: str | None = None,
    on_click: Callable[[], Any] | None = None,
    cta_key: str | None = None,
) -> bool:
    """P2 — title + reason + optional next-action. Returns True if the CTA was
    clicked. NEVER pass an internal filename/path as `desc`."""
    import streamlit as st

    safe_icon = escape(str(icon))
    safe_title = escape(str(title))
    safe_desc = escape(str(desc))
    st.markdown(
        f"<div class='ds-empty'><div style='font-size:22px;opacity:.6'>{safe_icon}</div>"
        f"<div class='t'>{safe_title}</div><div class='d'>{safe_desc}</div></div>",
        unsafe_allow_html=True,
    )
    if cta_label:
        clicked = st.button(cta_label, type="primary", key=cta_key)
        if clicked and on_click:
            on_click()
        return clicked
    return False


def notice(kind: str, title: str = "", body: str = "", action: str | None = None) -> None:
    """P3/P4 — the one container for user-facing messages. kind in
    {error,warn,info,ok}. `action` is optional remediation (markdown)."""
    import streamlit as st

    color, bg, ic = _NOTICE_STYLE.get(kind, _NOTICE_STYLE["info"])
    head = f"<strong>{escape(str(title))}</strong><br>" if title else ""
    act = f"<div style='margin-top:6px'>{escape(str(action))}</div>" if action else ""
    safe_body = escape(str(body))
    st.markdown(
        f"<div class='ds-notice' style='background:{bg};border-color:{color}33'>"
        f"<span class='ic' style='color:{color}'>{ic}</span>"
        f"<div>{head}{safe_body}{act}</div></div>",
        unsafe_allow_html=True,
    )


def error(message: str, remediation: str | None = None) -> None:
    """P3 — human error message + optional remediation. NEVER pass a raw
    exception/traceback/internal field name; use translate_error() first."""
    notice("error", body=message, action=remediation)


def translate_error(exc: Exception) -> tuple[str, str | None]:
    """P3 — map a known backend exception to (human_message, remediation).
    Falls back to a generic message; the raw text is logged, not shown."""
    logger.warning("ds.translate_error: %s", exc, exc_info=True)
    text = str(exc)
    text_lower = text.lower()
    # Known field-required cases (extend per app as needed).
    if "financing_mode" in text_lower:
        return (
            "Financing mode isn't set for this run.",
            "Choose a financing mode (e.g. per-path) and run again.",
        )
    if "exceeds total capital" in text_lower or "capital buffer" in text_lower:
        return (
            "The capital allocation isn't feasible.",
            "Reduce the internal allocation or volatility multiple to leave margin headroom.",
        )
    if "no investable funds" in text_lower or "no_funds" in text_lower:
        return (
            "No funds matched the selection filters.",
            "Try another preset or relax the selection settings.",
        )
    return (
        "Something went wrong running this step.",
        "Adjust the inputs and try again; if it persists, check the run logs.",
    )


def dev_note(msg: str) -> None:
    """P4 — dev/diagnostic state goes to logs, NEVER the main UI."""
    logger.info("ds.dev_note: %s", msg)


@contextmanager
def diagnostics_expander(label: str = "Diagnostics", *, expanded: bool = False):
    """P4 — explicit opt-in container for diagnostics that must be visible."""
    import streamlit as st

    with st.expander(label, expanded=expanded):
        yield


def availability_badge(label: str) -> str:
    """P5 — plain Streamlit-safe availability marker for tab titles/captions,
    e.g. tab label f"Export {availability_badge('multi-period only')}"."""
    return f" · {str(label).strip()}"


def humanize_id(raw: str, mapping: Mapping[str, str] | None = None) -> str:
    """P6 — decode an internal id to a human label; never show raw keys."""
    if mapping and raw in mapping:
        return mapping[raw]
    # Best-effort: take a trailing human-ish segment, strip hashes.
    tail = str(raw).replace("_", " ").split(":")[-1].strip()
    return tail or "item"
