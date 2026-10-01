"""
app.py — Streamlit dashboard
=============================
Reads last_values.json written by reader.py every 0.5 s.
No file upload. No large data in memory. Works on Streamlit Cloud or locally.

Run reader.py on the acquisition PC first, then open this app.
"""

import json
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import streamlit as st

# ── Config ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bridge STR Monitor", page_icon="🌉", layout="wide")

JSON_PATH       = Path(__file__).parent / "last_values.json"
POLL_INTERVAL_S = 0.5
HISTORY_SIZE    = 400   # ~200 s of history

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "last_ts":      None,
    "last_values":  None,
    "history":      None,
    "n_reads":      0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ────────────────────────────────────────────────────────────────────

def read_json() -> dict | None:
    """Read last_values.json. Returns None if missing or unchanged."""
    if not JSON_PATH.exists():
        return None
    with open(JSON_PATH) as f:
        return json.load(f)


def update_history(vals: dict) -> pd.DataFrame:
    row  = pd.DataFrame([vals], index=[pd.Timestamp.now(tz="UTC")])
    hist = st.session_state.history
    hist = pd.concat([hist, row]).tail(HISTORY_SIZE) if hist is not None else row
    st.session_state.history = hist
    return hist


def build_dashboard(vals: dict, hist: pd.DataFrame, filename: str) -> plt.Figure:
    channels = list(vals.keys())
    n        = len(channels)
    n_cols   = 6
    n_rows   = (n + n_cols - 1) // n_cols

    fig = plt.figure(figsize=(18, 3 * n_rows + 4), facecolor="#0e1117")

    all_v = np.array(list(vals.values()))
    med   = np.median(all_v)
    span  = max(np.abs(all_v - med).max(), 1.0)

    gs_top = gridspec.GridSpec(n_rows, n_cols, figure=fig,
                               top=0.97, bottom=0.38, hspace=0.5, wspace=0.35)
    gs_bot = gridspec.GridSpec(1, 1, figure=fig, top=0.30, bottom=0.05)

    for i, ch in enumerate(channels):
        v    = vals[ch]
        norm = min(abs(v - med) / span, 1.0)
        col  = (norm, 1.0 - norm * 0.7, 0.2)
        ax   = fig.add_subplot(gs_top[i // n_cols, i % n_cols])
        ax.set_facecolor("#1c1e26")
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")
        ax.text(0.5, 0.72, ch.replace("_", "\n", 1),
                ha="center", va="center", fontsize=7,
                color="#aaaaaa", transform=ax.transAxes, fontfamily="monospace")
        ax.text(0.5, 0.28, f"{v:+.1f} µε",
                ha="center", va="center", fontsize=11, fontweight="bold",
                color=col, transform=ax.transAxes)

    for i in range(n, n_rows * n_cols):
        fig.add_subplot(gs_top[i // n_cols, i % n_cols]).set_visible(False)

    ax_bot = fig.add_subplot(gs_bot[0])
    ax_bot.set_facecolor("#1c1e26")
    ax_bot.spines["top"].set_visible(False)
    ax_bot.spines["right"].set_visible(False)
    ax_bot.spines["left"].set_color("#555")
    ax_bot.spines["bottom"].set_color("#555")
    ax_bot.tick_params(colors="#888", labelsize=8)
    ax_bot.set_ylabel("µε", color="#888", fontsize=9)
    elapsed = (hist.index[-1] - hist.index[0]).total_seconds() if len(hist) > 1 else 0
    ax_bot.set_title(
        f"Last {len(hist)} reads ({elapsed:.0f} s) — {filename} @ {datetime.now().strftime('%H:%M:%S')}",
        color="#cccccc", fontsize=9, loc="left")
    cmap = plt.cm.tab20
    for j, ch in enumerate(channels):
        if ch in hist.columns:
            ax_bot.plot(hist.index, hist[ch], linewidth=0.9,
                        color=cmap(j / max(n - 1, 1)), label=ch, alpha=0.85)
    ax_bot.legend(fontsize=6, ncol=6, loc="upper left",
                  labelcolor="#cccccc", facecolor="#1c1e26",
                  edgecolor="#333", framealpha=0.7)
    ax_bot.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M:%S"))
    ax_bot.tick_params(axis="x", rotation=20, labelsize=7)
    fig.patch.set_facecolor("#0e1117")
    return fig


# ── Sidebar ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌉 Bridge STR Monitor")
    st.divider()
    st.markdown("### How it works")
    st.markdown(
        "**1.** Run `reader.py` on your acquisition PC:\n"
        "```\npython reader.py D:\\Sauvegarde\\Manuelle\n```\n"
        "**2.** It writes `last_values.json` every 0.5 s.\n\n"
        "**3.** This dashboard reads that JSON — no upload, no large file."
    )
    st.divider()
    st.markdown("**Live info**")
    info_ph = st.empty()


# ── Main ────────────────────────────────────────────────────────────────────────
st.title("🌉 Bridge STR Live Monitor")
status_bar = st.empty()
plot_area  = st.empty()

# Read JSON
data = read_json()

if data is None:
    status_bar.warning(
        "⏳ **Waiting for data…**\n\n"
        "Start `reader.py` on your acquisition PC:\n"
        "```\npython reader.py D:\\Sauvegarde\\Manuelle\n```\n"
        "It will write `last_values.json` next to `app.py`."
    )
    info_ph.markdown("- Status: waiting\n- Reads: 0")
    time.sleep(POLL_INTERVAL_S)
    st.rerun()

# Check if data is new
ts      = data["ts"]
changed = ts != st.session_state.last_ts

if changed:
    st.session_state.last_ts     = ts
    st.session_state.last_values = data["values"]
    st.session_state.n_reads    += 1
    update_history(data["values"])

vals     = st.session_state.last_values
filename = data["file"]
badge    = "🔄 **Updated**" if changed else "✅ **No change**"

status_bar.success(
    f"{badge}  |  📄 `{filename}`  |  "
    f"reads: **{st.session_state.n_reads}**  |  "
    f"last: **{ts[11:19]} UTC**"
)

with plot_area.container():
    fig = build_dashboard(vals, st.session_state.history, filename)
    st.pyplot(fig)
    plt.close(fig)

info_ph.markdown(
    f"- Status: live ✅\n"
    f"- File: `{filename}`\n"
    f"- Reads: `{st.session_state.n_reads}`\n"
    f"- Changed: {'yes 🔄' if changed else 'no ✅'}"
)

time.sleep(POLL_INTERVAL_S)
st.rerun()
