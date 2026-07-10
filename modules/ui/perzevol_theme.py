from __future__ import annotations

import html
from typing import Any

import streamlit as st


PALETTE = {
    "bg": "#08090c",
    "bg_2": "#101116",
    "panel": "rgba(255,255,255,0.035)",
    "panel_strong": "rgba(255,255,255,0.065)",
    "border": "rgba(255,255,255,0.12)",
    "red": "#ff4b4b",
    "green": "#30d158",
    "gold": "#ffd60a",
    "blue": "#0a84ff",
    "purple": "#bf5af2",
    "text": "#ffffff",
    "text_muted": "#c8c8c8",
    "text_dim": "#8f8f8f",
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def esc(value: Any) -> str:
    return html.escape(clean(value))


def compact_markup(markup: str) -> str:
    return "".join(
        line.strip()
        for line in str(markup or "").splitlines()
        if line.strip()
    )


def render_html(markup: str):
    st.markdown(compact_markup(markup), unsafe_allow_html=True)


def status_colour(status: str) -> str:
    status = clean(status).lower()

    if status in {"done", "complete", "completed", "green", "route worked", "progress banked"}:
        return "green"

    if status in {"current", "active", "moving", "in motion", "blue"}:
        return "blue"

    if status in {"priority", "push", "gold", "series", "story"}:
        return "gold"

    if status in {"experiment", "lab", "ttk", "purple", "started"}:
        return "purple"

    return "red"


def inject_perzevol_theme(*, clean_mode: bool = False, screen: str = "standard"):
    """
    Industrial AI Command Centre theme.

    Standard pages can scroll normally. Recording pages use viewport units and
    a fixed 100dvh frame so OBS captures the whole board without squashing
    everything into unreadable tiles.
    """
    hide_chrome = ""
    if clean_mode:
        hide_chrome = """
        [data-testid="stSidebar"] {display: none !important;}
        [data-testid="collapsedControl"] {display: none !important;}
        header {visibility: hidden !important; height: 0 !important;}
        #MainMenu {visibility: hidden !important;}
        footer {visibility: hidden !important; height: 0 !important;}
        """

    screen_css = ""

    if screen == "obs_record":
        screen_css = """
        html, body, .stApp {
            height: 100dvh;
            min-height: 100dvh;
            overflow: hidden !important;
        }

        .block-container {
            width: 100vw;
            max-width: 100vw;
            height: 100dvh;
            max-height: 100dvh;
            overflow: hidden !important;
            padding:
                clamp(0.35rem, 0.7vmin, 0.8rem)
                clamp(0.45rem, 0.9vmin, 1rem)
                clamp(0.35rem, 0.7vmin, 0.8rem)
                clamp(0.45rem, 0.9vmin, 1rem);
        }

        .stVerticalBlock,
        .element-container {
            gap: clamp(0.2rem, 0.42vmin, 0.45rem) !important;
        }

        div[data-testid="stButton"] > button {
            min-height: clamp(1.55rem, 3.15dvh, 2.2rem) !important;
            padding: 0.15rem 0.45rem !important;
            font-size: clamp(0.64rem, 0.95vmin, 0.86rem) !important;
            line-height: 1 !important;
        }

        .obs-command-bar {
            margin: 0 0 clamp(0.16rem, 0.34vmin, 0.38rem) 0;
            padding: clamp(0.24rem, 0.44vmin, 0.44rem) clamp(0.42rem, 0.8vmin, 0.78rem);
            min-height: 0;
        }

        .obs-command-label {
            font-size: clamp(0.62rem, 0.92vmin, 0.82rem);
            line-height: 1;
        }

        .obs-frame {
            height: calc(100dvh - clamp(4.6rem, 9.6dvh, 6.1rem));
            min-height: 0;
            overflow: hidden;
            display: grid;
            grid-template-rows: 16fr 52fr 32fr;
            gap: clamp(0.32rem, 0.7vmin, 0.7rem);
        }

        .obs-topline,
        .obs-primary,
        .obs-director,
        .obs-mini-card {
            border: 1px solid var(--pz-border);
            border-radius: 0;
            overflow: hidden;
            min-height: 0;
            background:
                radial-gradient(circle at top right, rgba(255,255,255,0.08), transparent 55%),
                linear-gradient(135deg, rgba(255,255,255,0.052), rgba(255,255,255,0.018));
        }

        .obs-topline {
            display: grid;
            grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
            gap: clamp(0.3rem, 0.65vmin, 0.65rem);
            border-left: clamp(0.35rem, 0.7vmin, 0.7rem) solid var(--pz-red);
            padding: clamp(0.42rem, 0.85vmin, 0.86rem);
        }

        .obs-title {
            color: var(--pz-text);
            font-size: clamp(1.8rem, 4.2vw, 5.2rem);
            font-weight: 950;
            letter-spacing: 0.08em;
            line-height: 0.85;
            text-transform: uppercase;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .obs-subtitle {
            color: var(--pz-red);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: clamp(0.56rem, 0.9vmin, 0.82rem);
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-top: clamp(0.18rem, 0.36vmin, 0.36rem);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .obs-stat-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: clamp(0.24rem, 0.5vmin, 0.55rem);
            align-self: stretch;
        }

        .obs-stat {
            background: rgba(0,0,0,0.30);
            border: 1px solid rgba(255,255,255,0.08);
            padding: clamp(0.28rem, 0.58vmin, 0.62rem);
            min-width: 0;
        }

        .obs-label {
            display: block;
            color: var(--pz-text-dim);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: clamp(0.48rem, 0.74vmin, 0.64rem);
            font-weight: 950;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: clamp(0.1rem, 0.24vmin, 0.22rem);
        }

        .obs-value {
            color: var(--pz-text);
            font-size: clamp(0.74rem, 1.1vmin, 1rem);
            font-weight: 950;
            line-height: 1.1;
            word-break: break-word;
        }

        .obs-mid {
            display: grid;
            grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
            gap: clamp(0.32rem, 0.7vmin, 0.7rem);
            min-height: 0;
        }

        .obs-primary {
            border-left: clamp(0.35rem, 0.7vmin, 0.7rem) solid var(--pz-blue);
            background:
                radial-gradient(circle at top right, rgba(10,132,255,0.24), transparent 52%),
                linear-gradient(135deg, rgba(10,132,255,0.10), rgba(255,255,255,0.022));
            padding: clamp(0.55rem, 1.05vmin, 1.05rem);
            display: grid;
            grid-template-rows: auto auto auto 1fr auto;
            gap: clamp(0.28rem, 0.55vmin, 0.55rem);
        }

        .obs-director {
            border-left: clamp(0.35rem, 0.7vmin, 0.7rem) solid var(--pz-gold);
            background:
                radial-gradient(circle at top right, rgba(255,214,10,0.20), transparent 55%),
                linear-gradient(135deg, rgba(255,214,10,0.08), rgba(255,255,255,0.022));
            padding: clamp(0.55rem, 1.05vmin, 1.05rem);
            display: grid;
            grid-template-rows: auto auto 1fr auto;
            gap: clamp(0.25rem, 0.55vmin, 0.55rem);
        }

        .obs-kicker {
            color: var(--pz-blue);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: clamp(0.52rem, 0.82vmin, 0.7rem);
            font-weight: 950;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        .obs-director .obs-kicker {
            color: var(--pz-gold);
        }

        .obs-headline {
            color: var(--pz-text);
            font-size: clamp(1.45rem, 3.35vw, 4.1rem);
            font-weight: 950;
            letter-spacing: 0.065em;
            line-height: 0.88;
            text-transform: uppercase;
            word-break: break-word;
        }

        .obs-director .obs-headline {
            font-size: clamp(1.15rem, 2.4vw, 2.8rem);
        }

        .obs-subhead {
            color: var(--pz-text-muted);
            font-size: clamp(0.72rem, 1.05vmin, 1rem);
            font-weight: 850;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            line-height: 1.1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .obs-textbox,
        .obs-rule,
        .obs-proof-item {
            background: rgba(0,0,0,0.28);
            border: 1px solid rgba(255,255,255,0.08);
            padding: clamp(0.36rem, 0.72vmin, 0.72rem);
            color: var(--pz-text-muted);
            font-size: clamp(0.68rem, 1.05vmin, 0.94rem);
            line-height: 1.22;
            min-height: 0;
        }

        .obs-textbox p,
        .obs-proof-item p {
            margin: 0;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .obs-rule {
            border-color: rgba(255,75,75,0.34);
            border-left: clamp(0.25rem, 0.5vmin, 0.48rem) solid var(--pz-red);
            background: rgba(255,75,75,0.12);
            color: var(--pz-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: clamp(0.58rem, 0.9vmin, 0.8rem);
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .obs-bottom {
            display: grid;
            grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr) minmax(0, 0.7fr);
            gap: clamp(0.32rem, 0.7vmin, 0.7rem);
            min-height: 0;
        }

        .obs-mini-card {
            padding: clamp(0.48rem, 0.9vmin, 0.9rem);
            display: grid;
            grid-template-rows: auto auto 1fr;
            gap: clamp(0.2rem, 0.45vmin, 0.45rem);
        }

        .obs-mini-card.green {
            border-left: clamp(0.32rem, 0.65vmin, 0.6rem) solid var(--pz-green);
        }

        .obs-mini-card.gold {
            border-left: clamp(0.32rem, 0.65vmin, 0.6rem) solid var(--pz-gold);
        }

        .obs-mini-card.red {
            border-left: clamp(0.32rem, 0.65vmin, 0.6rem) solid var(--pz-red);
        }

        .obs-mini-title {
            color: var(--pz-text);
            font-size: clamp(1rem, 2vw, 2.2rem);
            font-weight: 950;
            line-height: 0.95;
            letter-spacing: 0.055em;
            text-transform: uppercase;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .obs-mini-body {
            color: var(--pz-text-muted);
            font-size: clamp(0.65rem, 0.98vmin, 0.9rem);
            line-height: 1.2;
            overflow: hidden;
        }

        .obs-proof-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: clamp(0.22rem, 0.45vmin, 0.48rem);
            min-height: 0;
        }

        .obs-proof-item {
            padding: clamp(0.28rem, 0.58vmin, 0.58rem);
        }

        .obs-proof-item .obs-label {
            color: var(--pz-gold);
        }

        @media (max-aspect-ratio: 4/3) {
            .obs-frame {
                grid-template-rows: 14fr 56fr 30fr;
            }

            .obs-topline,
            .obs-mid,
            .obs-bottom {
                grid-template-columns: 1fr;
            }

            .obs-stat-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        """

    if screen == "finish_line":
        screen_css = """
        html, body, .stApp {
            min-height: 100dvh;
            height: auto;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        .block-container {
            width: 100vw;
            max-width: 100vw;
            min-height: 100dvh;
            height: auto;
            max-height: none;
            overflow: visible !important;
            padding:
                clamp(0.45rem, 0.9vmin, 1rem)
                clamp(0.55rem, 1.05vmin, 1.2rem)
                clamp(0.45rem, 0.9vmin, 1rem)
                clamp(0.55rem, 1.05vmin, 1.2rem);
        }

        .finish-hero {
            padding: clamp(0.72rem, 1.18vmin, 1.15rem);
            margin-bottom: clamp(0.42rem, 0.8vmin, 0.82rem);
        }

        .finish-kicker {
            font-size: clamp(0.62rem, 0.92vmin, 0.82rem);
        }

        .finish-title {
            font-size: clamp(3.2rem, 6.2vw, 7.4rem);
            line-height: 0.82;
            margin-top: clamp(0.18rem, 0.42vmin, 0.45rem);
        }

        .finish-subtitle {
            font-size: clamp(0.78rem, 1.08vmin, 1rem);
            margin-top: clamp(0.35rem, 0.7vmin, 0.72rem);
        }

        .progress-rail {
            height: clamp(0.75rem, 1.45vmin, 1.25rem);
            margin-top: clamp(0.38rem, 0.72vmin, 0.72rem);
        }

        .metric-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: clamp(0.32rem, 0.62vmin, 0.62rem);
            margin-top: clamp(0.48rem, 0.88vmin, 0.88rem);
        }

        .metric {
            padding: clamp(0.48rem, 0.8vmin, 0.78rem);
        }

        .metric-label {
            font-size: clamp(0.52rem, 0.76vmin, 0.64rem);
        }

        .metric-value {
            font-size: clamp(1.1rem, 1.95vw, 2.35rem);
            line-height: 0.96;
            margin-top: clamp(0.2rem, 0.4vmin, 0.4rem);
        }

        .metric-note {
            font-size: clamp(0.58rem, 0.78vmin, 0.72rem);
            line-height: 1.15;
        }

        .quote {
            padding: clamp(0.48rem, 0.84vmin, 0.82rem);
            margin-top: clamp(0.42rem, 0.78vmin, 0.78rem);
            font-size: clamp(1.05rem, 1.8vw, 2rem);
            line-height: 1.02;
        }

        .section-title {
            font-size: clamp(0.84rem, 1.18vmin, 1.05rem);
            margin: clamp(0.4rem, 0.72vmin, 0.7rem) 0 clamp(0.3rem, 0.55vmin, 0.55rem) 0;
        }

        .check-grid {
            grid-template-columns: repeat(auto-fit, minmax(clamp(11rem, 13.8vw, 15rem), 1fr));
            gap: clamp(0.28rem, 0.56vmin, 0.56rem);
            max-height: none;
            overflow: visible;
        }

        .check-card {
            min-height: 0;
            padding: clamp(0.45rem, 0.72vmin, 0.7rem);
        }

        .check-label {
            font-size: clamp(0.72rem, 0.98vmin, 0.92rem);
        }

        .check-status {
            font-size: clamp(0.48rem, 0.68vmin, 0.58rem);
        }

        .check-count {
            font-size: clamp(1rem, 1.65vw, 1.9rem);
            margin-top: clamp(0.22rem, 0.42vmin, 0.42rem);
        }

        .check-note {
            font-size: clamp(0.56rem, 0.76vmin, 0.7rem);
            line-height: 1.14;
            min-height: 0;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .mini-bar {
            height: clamp(0.3rem, 0.56vmin, 0.52rem);
            margin-top: clamp(0.22rem, 0.44vmin, 0.42rem);
        }

        .priority-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(clamp(12rem, 17vw, 20rem), 1fr));
            gap: clamp(0.28rem, 0.56vmin, 0.56rem);
            max-height: none;
            overflow: visible;
        }

        .priority-card {
            padding: clamp(0.42rem, 0.7vmin, 0.66rem);
            margin-bottom: 0;
        }

        .priority-title {
            font-size: clamp(0.72rem, 0.95vmin, 0.9rem);
            line-height: 1.08;
        }

        .priority-meta {
            font-size: clamp(0.54rem, 0.74vmin, 0.68rem);
        }

        div[data-testid="stCaptionContainer"] {
            font-size: clamp(0.54rem, 0.74vmin, 0.68rem);
        }
        """

    if screen == "ttk_oracle":
        screen_css = """
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(191,90,242,0.20), transparent 30%),
                radial-gradient(circle at bottom right, rgba(255,214,10,0.12), transparent 32%),
                linear-gradient(135deg, var(--pz-bg) 0%, #0b0910 48%, #050508 100%);
        }

        h1, h2, h3,
        .pz-page-title {
            color: var(--pz-purple) !important;
        }

        .pz-page-card,
        div[data-testid="stExpander"] {
            border-left-color: var(--pz-purple) !important;
        }
        """

    render_html(
        f"""
        <style>
        :root {{
            --pz-bg: {PALETTE["bg"]};
            --pz-bg-2: {PALETTE["bg_2"]};
            --pz-panel: {PALETTE["panel"]};
            --pz-panel-strong: {PALETTE["panel_strong"]};
            --pz-border: {PALETTE["border"]};
            --pz-red: {PALETTE["red"]};
            --pz-green: {PALETTE["green"]};
            --pz-gold: {PALETTE["gold"]};
            --pz-blue: {PALETTE["blue"]};
            --pz-purple: {PALETTE["purple"]};
            --pz-text: {PALETTE["text"]};
            --pz-text-muted: {PALETTE["text_muted"]};
            --pz-text-dim: {PALETTE["text_dim"]};
        }}

        html, body, .stApp {{
            background: var(--pz-bg);
            color: var(--pz-text);
        }}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(255,75,75,0.14), transparent 32%),
                radial-gradient(circle at bottom right, rgba(10,132,255,0.10), transparent 34%),
                linear-gradient(135deg, var(--pz-bg) 0%, var(--pz-bg-2) 52%, #030405 100%);
        }}

        .block-container {{
            max-width: min(96vw, 1920px);
            padding-top: clamp(0.8rem, 1.6vmin, 1.7rem);
            padding-bottom: clamp(0.9rem, 1.8vmin, 1.9rem);
            padding-left: clamp(0.9rem, 2vw, 2.4rem);
            padding-right: clamp(0.9rem, 2vw, 2.4rem);
        }}

        {hide_chrome}

        h1, h2, h3, h4,
        .pz-page-title,
        .commander-title,
        .finish-title,
        .record-title,
        .card-title,
        .section-title {{
            color: var(--pz-text);
            font-weight: 950 !important;
            letter-spacing: 0.055em;
            text-transform: uppercase;
        }}

        h1 {{
            font-size: clamp(2rem, 3vw, 3.6rem) !important;
            line-height: 0.95 !important;
        }}

        h2 {{
            font-size: clamp(1.35rem, 2vw, 2.25rem) !important;
        }}

        h3 {{
            font-size: clamp(1.05rem, 1.45vw, 1.55rem) !important;
        }}

        p, label, .stMarkdown, .stCaptionContainer {{
            color: var(--pz-text-muted);
        }}

        code, pre,
        .pz-kicker,
        .finish-kicker,
        .eyebrow,
        .metric-label,
        .check-status,
        .mode-head,
        .commander-subtitle,
        .record-subtitle {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
            letter-spacing: 0.13em;
            text-transform: uppercase;
        }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #050608, #0d0e13) !important;
            border-right: 1px solid var(--pz-border);
        }}

        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.35rem;
            border-bottom: 1px solid var(--pz-border);
        }}

        .stTabs [data-baseweb="tab"] {{
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(255,255,255,0.08);
            border-bottom: none;
            color: var(--pz-text-dim);
            font-weight: 900;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .stTabs [aria-selected="true"] {{
            color: var(--pz-text) !important;
            background: rgba(255,75,75,0.14) !important;
            border-color: rgba(255,75,75,0.35) !important;
        }}

        div[data-testid="stMetric"] {{
            background: var(--pz-panel);
            border: 1px solid var(--pz-border);
            border-left: 0.45rem solid var(--pz-blue);
            padding: clamp(0.65rem, 1vmin, 0.95rem);
        }}

        div[data-testid="stMetric"] label {{
            color: var(--pz-text-dim) !important;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace !important;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }}

        div[data-testid="stMetricValue"] {{
            color: var(--pz-text) !important;
            font-size: clamp(1.55rem, 2.2vw, 2.8rem) !important;
            font-weight: 950 !important;
        }}

        div[data-testid="stButton"] > button,
        div[data-testid="baseButton-secondary"] {{
            background: rgba(255,255,255,0.045) !important;
            color: var(--pz-text) !important;
            border: 1px solid rgba(255,255,255,0.16) !important;
            border-radius: 0 !important;
            font-weight: 950 !important;
            letter-spacing: 0.08em !important;
            text-transform: uppercase !important;
            min-height: clamp(2.1rem, 4vmin, 2.8rem);
        }}

        div[data-testid="stButton"] > button:hover {{
            border-color: var(--pz-red) !important;
            background: rgba(255,75,75,0.14) !important;
        }}

        input, textarea,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] {{
            background: rgba(0,0,0,0.28) !important;
            color: var(--pz-text) !important;
            border-color: rgba(255,255,255,0.14) !important;
            border-radius: 0 !important;
        }}

        div[data-testid="stDataFrame"],
        div[data-testid="stTable"],
        div[data-testid="stExpander"] {{
            border: 1px solid var(--pz-border);
            background: rgba(0,0,0,0.18);
        }}

        div[data-testid="stExpander"] {{
            border-left: 0.45rem solid var(--pz-gold);
        }}

        .pz-page-card,
        .matrix-wrap,
        .plan-card,
        .record-shell,
        .hero-card,
        .finish-hero,
        .metric,
        .check-card,
        .priority-card,
        .obs-command-bar {{
            border: 1px solid var(--pz-border);
            border-radius: 0;
            background:
                linear-gradient(135deg, rgba(255,255,255,0.055), rgba(255,255,255,0.018));
            box-shadow: none;
        }}

        .record-shell {{
            background: rgba(0,0,0,0.24);
            border-left: 0.55rem solid var(--pz-red);
        }}

        .record-title {{
            font-size: clamp(2.2rem, 4.5vw, 5.6rem);
            line-height: 0.9;
        }}

        .record-subtitle {{
            color: var(--pz-red);
            font-size: clamp(0.78rem, 1.15vw, 1rem);
            margin-top: 0.4rem;
        }}

        .hero-card {{
            border-left: 0.65rem solid var(--pz-red);
            background:
                radial-gradient(circle at top right, rgba(255,75,75,0.18), rgba(255,255,255,0.03) 44%, transparent 70%),
                linear-gradient(135deg, rgba(255,255,255,0.055), rgba(255,255,255,0.02));
            padding: clamp(0.8rem, 1.25vmin, 1.25rem);
            margin: 0.75rem 0;
        }}

        .blue-card {{
            border-left-color: var(--pz-blue);
            background:
                radial-gradient(circle at top right, rgba(10,132,255,0.20), transparent 50%),
                linear-gradient(135deg, rgba(10,132,255,0.09), rgba(255,255,255,0.025));
        }}

        .green-card {{
            border-left-color: var(--pz-green);
            background:
                radial-gradient(circle at top right, rgba(48,209,88,0.18), transparent 50%),
                linear-gradient(135deg, rgba(48,209,88,0.08), rgba(255,255,255,0.025));
        }}

        .gold-card {{
            border-left-color: var(--pz-gold);
            background:
                radial-gradient(circle at top right, rgba(255,214,10,0.18), transparent 50%),
                linear-gradient(135deg, rgba(255,214,10,0.08), rgba(255,255,255,0.025));
        }}

        .purple-card {{
            border-left-color: var(--pz-purple);
            background:
                radial-gradient(circle at top right, rgba(191,90,242,0.20), transparent 50%),
                linear-gradient(135deg, rgba(191,90,242,0.08), rgba(255,255,255,0.025));
        }}

        .eyebrow,
        .finish-kicker {{
            color: var(--pz-red);
            font-size: 0.76rem;
            font-weight: 950;
            margin-bottom: 0.35rem;
        }}

        .blue-card .eyebrow {{ color: var(--pz-blue); }}
        .green-card .eyebrow {{ color: var(--pz-green); }}
        .gold-card .eyebrow {{ color: var(--pz-gold); }}
        .purple-card .eyebrow {{ color: var(--pz-purple); }}

        .card-title {{
            color: var(--pz-text);
            font-size: clamp(1.75rem, 2.75vw, 3.5rem);
            line-height: 0.98;
        }}

        .card-subtitle {{
            color: var(--pz-text-muted);
            font-weight: 820;
            letter-spacing: 0.07em;
            text-transform: uppercase;
            margin-top: 0.35rem;
        }}

        .stat-grid,
        .metric-grid,
        .check-grid,
        .shot-grid {{
            display: grid;
            gap: 0.65rem;
        }}

        .stat-grid {{
            grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
            margin-top: 0.85rem;
        }}

        .stat-grid div,
        .shot,
        .detail {{
            background: rgba(0,0,0,0.28);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.68rem 0.75rem;
        }}

        .stat-grid span,
        .detail span,
        .shot span {{
            display: block;
            color: var(--pz-text-dim);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 0.66rem;
            font-weight: 900;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 0.22rem;
        }}

        .stat-grid strong {{
            color: var(--pz-text);
            font-size: 0.98rem;
            font-weight: 950;
        }}

        .detail {{
            margin-top: 0.75rem;
        }}

        .detail p,
        .shot p {{
            color: var(--pz-text-muted);
            line-height: 1.34;
            margin: 0;
        }}

        .rule,
        .quote,
        .obs-command-bar {{
            border: 1px solid rgba(255,75,75,0.32);
            border-left: 0.55rem solid var(--pz-red);
            background: rgba(255,75,75,0.11);
            color: var(--pz-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        .rule {{
            padding: 0.62rem 0.78rem;
            margin-top: 0.85rem;
        }}

        .obs-command-bar {{
            padding: 0.55rem 0.75rem;
            margin-bottom: 0.55rem;
        }}

        .obs-command-label {{
            color: var(--pz-text);
            font-weight: 950;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }}

        .shot-grid {{
            grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
            margin-top: 0.75rem;
        }}

        .shot span {{
            color: var(--pz-gold);
        }}

        .morale-banner {{
            border: 1px solid rgba(255,75,75,0.42);
            background: rgba(255,75,75,0.10);
            padding: 0.75rem 0.85rem;
            margin: 0 0 0.8rem 0;
        }}

        .morale-banner strong {{
            display: block;
            color: var(--pz-text);
            font-size: clamp(1.25rem, 2vw, 2rem);
            font-weight: 950;
            letter-spacing: 0.06em;
            line-height: 1;
            text-transform: uppercase;
        }}

        .morale-banner span {{
            display: block;
            color: var(--pz-text-muted);
            margin-top: 0.32rem;
        }}

        .finish-hero {{
            border-left: 0.75rem solid var(--pz-red);
            background:
                radial-gradient(circle at top right, rgba(255,75,75,0.28), rgba(255,75,75,0.05) 38%, transparent 70%),
                linear-gradient(135deg, rgba(255,255,255,0.07), rgba(255,255,255,0.022));
        }}

        .finish-title {{
            color: var(--pz-text);
            font-size: clamp(3rem, 7vw, 7rem);
            line-height: 0.85;
        }}

        .finish-subtitle {{
            color: var(--pz-text-muted);
            font-size: clamp(0.95rem, 1.25vw, 1.18rem);
        }}

        .metric-grid {{
            grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
            margin-top: 0.9rem;
        }}

        .metric {{
            background: rgba(0,0,0,0.30);
            padding: 0.8rem 0.85rem;
        }}

        .metric-label {{
            color: var(--pz-text-dim);
            font-size: 0.68rem;
            font-weight: 900;
        }}

        .metric-value {{
            color: var(--pz-text);
            font-size: clamp(1.35rem, 2.25vw, 2.55rem);
            font-weight: 950;
            line-height: 1;
            margin-top: 0.4rem;
        }}

        .metric-note {{
            color: var(--pz-text-muted);
            font-size: 0.8rem;
            margin-top: 0.32rem;
        }}

        .progress-rail {{
            height: 1.25rem;
            background: rgba(255,255,255,0.09);
            border: 1px solid rgba(255,255,255,0.12);
            margin-top: 0.8rem;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--pz-red), var(--pz-gold), var(--pz-green));
        }}

        .section-title {{
            color: var(--pz-text);
            font-size: 1.2rem;
            margin: 1rem 0 0.6rem 0;
        }}

        .check-grid {{
            grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
        }}

        .check-card {{
            background: var(--pz-panel);
            padding: 0.75rem 0.82rem;
        }}

        .check-card.done {{ border-left: 0.45rem solid var(--pz-green); }}
        .check-card.push {{ border-left: 0.45rem solid var(--pz-gold); }}
        .check-card.moving {{ border-left: 0.45rem solid var(--pz-blue); }}
        .check-card.started {{ border-left: 0.45rem solid var(--pz-purple); }}
        .check-card.empty {{ border-left: 0.45rem solid var(--pz-red); }}

        .check-top {{
            display: flex;
            justify-content: space-between;
            gap: 0.55rem;
            align-items: flex-start;
        }}

        .check-label {{
            color: var(--pz-text);
            font-weight: 950;
            line-height: 1.1;
        }}

        .check-status {{
            color: var(--pz-text);
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            font-size: 0.62rem;
            font-weight: 950;
            padding: 0.2rem 0.34rem;
            white-space: nowrap;
        }}

        .check-count {{
            color: var(--pz-text);
            font-size: 1.6rem;
            font-weight: 950;
            margin-top: 0.45rem;
        }}

        .check-note {{
            color: var(--pz-text-muted);
            font-size: 0.78rem;
            margin-top: 0.25rem;
        }}

        .mini-bar {{
            height: 0.55rem;
            background: rgba(255,255,255,0.09);
            margin-top: 0.55rem;
            overflow: hidden;
        }}

        .mini-fill {{
            height: 100%;
            background: var(--pz-green);
        }}

        .quote {{
            padding: 0.85rem 1rem;
            margin-top: 0.85rem;
            font-size: clamp(1.15rem, 2vw, 2.1rem);
            line-height: 1.05;
        }}

        .priority-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
            gap: 0.6rem;
        }}

        .priority-card {{
            border-left: 0.45rem solid var(--pz-gold);
            background: rgba(255,214,10,0.07);
            padding: 0.7rem 0.8rem;
        }}

        .priority-title {{
            color: var(--pz-text);
            font-weight: 950;
        }}

        .priority-meta {{
            color: var(--pz-text-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            font-size: 0.76rem;
            margin-top: 0.22rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }}

        .commander-title {{
            color: var(--pz-text);
            font-size: clamp(2.2rem, 4vw, 4.6rem);
            line-height: 0.9;
        }}

        .commander-subtitle {{
            color: var(--pz-text-muted);
            font-size: 0.95rem;
        }}

        .matrix-wrap {{
            background: var(--pz-panel);
            border-left: 0.55rem solid var(--pz-blue);
        }}

        .mode-head {{
            color: var(--pz-red);
        }}

        .plan-card {{
            border-left: 0.65rem solid var(--pz-green);
            background:
                radial-gradient(circle at top right, rgba(48,209,88,0.16), transparent 50%),
                linear-gradient(135deg, rgba(48,209,88,0.08), rgba(255,255,255,0.025));
        }}

        @media (max-width: 900px) {{
            .metric-grid,
            .stat-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}

            .shot-grid,
            .check-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        {screen_css}
        </style>
        """
    )


def render_command_card(
    *,
    kicker: str,
    title: str,
    subtitle: str = "",
    body: str = "",
    status: str = "red",
):
    colour = status_colour(status)
    render_html(
        f"""
        <div class="hero-card {colour}-card">
            <div class="eyebrow">{esc(kicker)}</div>
            <div class="card-title">{esc(title)}</div>
            {f'<div class="card-subtitle">{esc(subtitle)}</div>' if subtitle else ''}
            {f'<div class="detail"><p>{esc(body)}</p></div>' if body else ''}
        </div>
        """
    )


def render_metric_tile(label: str, value: str, note: str = ""):
    render_html(
        f"""
        <div class="metric">
            <div class="metric-label">{esc(label)}</div>
            <div class="metric-value">{esc(value)}</div>
            {f'<div class="metric-note">{esc(note)}</div>' if note else ''}
        </div>
        """
    )


def render_rule_banner(text: str, *, status: str = "red"):
    colour = PALETTE.get(status_colour(status), PALETTE["red"])
    render_html(
        f"""
        <div class="rule" style="border-left-color:{colour};">
            {esc(text)}
        </div>
        """
    )


def render_bucket_card(
    *,
    label: str,
    done: int,
    total: int,
    status: str,
    note: str = "",
    percent: float = 0.0,
):
    css_status = status_colour(status)
    render_html(
        f"""
        <div class="check-card {css_status}">
            <div class="check-top">
                <div class="check-label">{esc(label)}</div>
                <div class="check-status">{esc(status)}</div>
            </div>
            <div class="check-count">{int(done)}/{int(total)}</div>
            {f'<div class="check-note">{esc(note)}</div>' if note else ''}
            <div class="mini-bar"><div class="mini-fill" style="width:{max(0, min(100, float(percent))):.1f}%;"></div></div>
        </div>
        """
    )
