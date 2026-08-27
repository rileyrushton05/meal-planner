"""Theme tokens and the CSS that applies them to Streamlit's widgets."""

from __future__ import annotations

import streamlit as st

from app.models import DayOfWeek

BG_COLOR = "#14151D"
SURFACE = "#1C1E27"
BORDER = "#2B2E3A"
TEXT_COLOR = "#E5E7EB"
TEXT_MUTED = "#9CA3AF"
ACCENT_COLOR = "#818CF8"
ACCENT_HOVER = "#6366F1"
ACCENT_CONTRAST = "#14151D"

#: One saturated colour per day, the only place strong colour is used. Keyed
#: by enum so a day can never be spelled wrong here.
DAY_COLORS: dict[DayOfWeek, str] = {
    DayOfWeek.MONDAY: "#6366F1",
    DayOfWeek.TUESDAY: "#0D9488",
    DayOfWeek.WEDNESDAY: "#D97706",
    DayOfWeek.THURSDAY: "#2563EB",
    DayOfWeek.FRIDAY: "#DB2777",
    DayOfWeek.SATURDAY: "#16A34A",
    DayOfWeek.SUNDAY: "#7C3AED",
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Manrope:wght@400;500;600;700&display=swap');

/* Colours are forced here rather than left to .streamlit/config.toml alone.
   That file is found relative to the launching process's working directory,
   which differs between a terminal and some IDE run buttons, so on its own
   it isn't reliable. */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stHeader"] {{
    background-color: {BG_COLOR} !important;
    color: {TEXT_COLOR} !important;
}}

html, body, [class*="css"] {{
    font-family: 'Manrope', system-ui, sans-serif;
}}

/* Every button is indigo by default, with the muted look for
   Delete/Remove carved back out via kind="secondary" below. Matching
   kind="primary" directly proved unreliable - the attribute differs
   between form-submit buttons and plain ones across Streamlit versions. */
[data-testid="stAppViewContainer"] .stButton button,
[data-testid="stAppViewContainer"] .stFormSubmitButton button {{
    background-color: {ACCENT_COLOR} !important;
    border-color: {ACCENT_COLOR} !important;
    color: {ACCENT_CONTRAST} !important;
}}
[data-testid="stAppViewContainer"] .stButton button p,
[data-testid="stAppViewContainer"] .stFormSubmitButton button p {{
    color: {ACCENT_CONTRAST} !important;
}}
[data-testid="stAppViewContainer"] .stButton button:hover,
[data-testid="stAppViewContainer"] .stFormSubmitButton button:hover {{
    background-color: {ACCENT_HOVER} !important;
    border-color: {ACCENT_HOVER} !important;
}}
[data-testid="stAppViewContainer"] .stButton button:hover p,
[data-testid="stAppViewContainer"] .stFormSubmitButton button:hover p {{
    color: #FFFFFF !important;
}}

[data-testid="stAppViewContainer"] button[kind="secondary"] {{
    background-color: {SURFACE} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT_MUTED} !important;
}}
[data-testid="stAppViewContainer"] button[kind="secondary"] p {{
    color: {TEXT_MUTED} !important;
}}
[data-testid="stAppViewContainer"] button[kind="secondary"]:hover {{
    background-color: {BORDER} !important;
    border-color: {TEXT_MUTED} !important;
    color: {TEXT_COLOR} !important;
}}

div.stButton > button, div.stFormSubmitButton > button {{
    font-family: 'Manrope', system-ui, sans-serif;
    font-weight: 700;
    font-size: 0.88rem;
    border-radius: 8px;
    padding: 0.6rem 1.15rem;
}}

h1 {{
    font-family: 'Sora', system-ui, sans-serif;
    font-weight: 700;
    font-size: 2.1rem;
    letter-spacing: -0.01em;
    color: {TEXT_COLOR};
}}
h3 {{
    font-family: 'Sora', system-ui, sans-serif;
    font-weight: 700;
    font-size: 1.15rem;
    color: {TEXT_COLOR};
}}

[data-testid="stCaptionContainer"] {{
    color: {TEXT_MUTED} !important;
}}

[data-baseweb="tab-highlight"] {{
    background-color: {ACCENT_COLOR} !important;
}}
.stTabs [data-baseweb="tab-list"] button {{
    font-family: 'Sora', system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.95rem;
}}
.stTabs [data-baseweb="tab-list"] button p {{
    color: {TEXT_MUTED} !important;
}}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] p {{
    color: {ACCENT_COLOR} !important;
}}

[data-testid="stWidgetLabel"] p {{
    font-family: 'Manrope', system-ui, sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: {TEXT_MUTED};
}}

.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {{
    font-family: 'Manrope', system-ui, sans-serif;
    font-size: 0.92rem;
    border-radius: 8px !important;
}}

/* Input fills are set explicitly too: left alone they follow whatever
   base light/dark theme Streamlit computed internally, independent of the
   page background above, giving a dark-box-on-light-page mismatch. */
[data-testid="stTextInput"] div[data-baseweb="base-input"],
[data-testid="stNumberInput"] div[data-baseweb="base-input"],
.stSelectbox div[data-baseweb="select"] > div {{
    background-color: {SURFACE} !important;
    border-color: {BORDER} !important;
}}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
.stSelectbox div[data-baseweb="select"] * {{
    color: {TEXT_COLOR} !important;
    background-color: transparent !important;
}}

/* The select dropdown is portalled outside stAppViewContainer, so it
   needs its own unscoped rule. */
[data-baseweb="popover"] [data-baseweb="menu"] {{
    background-color: {SURFACE} !important;
}}
[data-baseweb="popover"] [data-baseweb="menu"] li {{
    color: {TEXT_COLOR} !important;
}}

[data-testid="stForm"] {{
    border-radius: 10px;
    padding: 1.25rem;
    background-color: {SURFACE};
    border: 1px solid {BORDER};
}}

div[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 10px !important;
    background-color: {SURFACE};
    border: 1px solid {BORDER} !important;
}}

hr {{
    border-color: {BORDER} !important;
    margin: 2rem 0 !important;
}}

.day-card {{
    border-radius: 10px;
    padding: 0.95rem 0.6rem;
    text-align: center;
    color: #FFFFFF;
}}
.day-card .day-name {{
    font-family: 'Manrope', system-ui, sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.85;
}}
.day-card .meal-name {{
    font-family: 'Sora', system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.88rem;
    margin-top: 0.4rem;
    line-height: 1.25;
}}

.grocery-row {{
    border-radius: 10px;
    padding: 0.75rem 1.1rem;
    margin-bottom: 0.6rem;
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: {TEXT_COLOR};
    font-family: 'Manrope', system-ui, sans-serif;
}}
.grocery-row .qty {{
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    font-size: 0.9rem;
    color: {ACCENT_COLOR};
}}
</style>
"""


def inject_theme() -> None:
    """Apply the app's colours and typography. Call once per page load."""
    st.markdown(_CSS, unsafe_allow_html=True)
