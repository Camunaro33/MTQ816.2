"""
Bridge STR Live Monitor — Streamlit App
========================================
Watches a folder for the most-recent .tdms file, polls it every 0.5 s,
and re-renders the STR strain-gauge plots only when the file actually changes.

Usage
-----
    streamlit run app.py

The watched folder is configured via the sidebar (default: D:\\Sauvegarde\\Manuelle).
"""

import os
import time
import glob
import hashlib
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import streamlit as st
from nptdms import TdmsFile

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bridge STR Monitor",
    page_icon="🌉",
    layout="wide",
)

# ── Constants ─────────────────────────────────────────────────────────────────
STR_PREFIX        = "STR"
POLL_INTERVAL_S   = 0.5          # seconds between file checks
DEFAULT_FOLDER    = r"D:\Sauvegarde\Manuelle"


# ── Session-state initialisation ──────────────────────────────────────────────
def _init_state():
    defaults = {
        "last_hash":     None,   # md5 of last-read file
        "last_path":     None,   # path of last-read file
        "df":            None,   # current DataFrame
        "last_updated":  None,   # human-readable timestamp
        "error":         None,   # last error string
        "n_refreshes":   0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_latest_tdms(folder: str) -> Path | None:
    """Return the most-recently modified .tdms file in *folder*, or None."""
    pattern = os.path.join(folder, "**", "*.tdms")
    files = glob.glob(pattern, recursive=True)
    if not files:
        pattern_flat = os.path.join(folder, "*.tdms")
        files = glob.glob(pattern_flat)
    if not files:
        return None
    return Path(max(files, key=os.path.getmtime))


def file_md5(path: Path) -> str:
    """Fast partial hash (first + last 64 kB + mtime) to detect changes."""
    stat  = path.stat()
    mtime = str(stat.st_mtime).encode()
    size  = str(stat.st_size).encode()
    h = hashlib.md5(mtime + size)
    with open(path, "rb") as f:
        h.update(f.read(65536))
        f.seek(-min(65536, stat.st_size), 2)
        h.update(f.read())
    return h.hexdigest()


def load_str_channels(path: Path) -> pd.DataFrame:
    """Read TDMS and return DataFrame of all STR channels with DatetimeIndex."""
    tf = TdmsFile.read(str(path))
    channels = [
        ch
        for group in tf.groups()
        for ch in group.channels()
        if ch.name.upper().startswith(STR_PREFIX)
    ]
    if not channels:
        raise ValueError(f"No '{STR_PREFIX}*' channels found in {path.name}.")

    ref       = channels[0]
    t0        = pd.Timestamp(ref.properties["wf_start_time"], tz="UTC")
    increment = ref.properties["wf_increment"]
    n         = len(ref[:])
    index     = pd.date_range(
        start   = t0,
        periods = n,
        freq    = pd.tseries.frequencies.to_offset(pd.Timedelta(seconds=increment)),
    )

    df = pd.DataFrame({ch.name: ch[:] for ch in channels}, index=index)
    df.index.name = "timestamp_utc"
    return df


def build_figure(df: pd.DataFrame) -> plt.Figure:
    """Return a Matplotlib figure with one subplot per STR channel."""
    cols   = df.columns.tolist()
    n      = len(cols)
    n_cols = 3
    n_rows = (n + n_cols - 1) // n_cols

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(6 * n_cols, 3 * n_rows),
        sharex=True,
        constrained_layout=True,
    )
    axes_flat = np.array(axes).flatten()

    for ax, col in zip(axes_flat, cols):
        ax.plot(df.index, df[col], linewidth=0.8, color="#2196F3")
        ax.set_title(col, fontsize=9, fontweight="bold")
        ax.set_ylabel("µε", fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        ax.tick_params(axis="x", labelsize=7, rotation=30)
        ax.grid(True, linestyle="--", alpha=0.4)

    for ax in axes_flat[n:]:
        ax.set_visible(False)

    fig.suptitle(
        f"Bridge STR Channels  —  {df.index[0].strftime('%Y-%m-%d  %H:%M:%S UTC')}",
        fontsize=13, fontweight="bold",
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌉 Bridge STR Monitor")
    folder = st.text_input(
        "Acquisition folder",
        value=DEFAULT_FOLDER,
        help="Folder that contains .tdms files (sub-folders included).",
    )
    st.caption(f"Polls every **{POLL_INTERVAL_S} s**. Plot refreshes only when file changes.")
    st.divider()
    st.markdown("**Session info**")
    info_box = st.empty()


# ── Main layout ───────────────────────────────────────────────────────────────
st.title("🌉 Bridge STR Live Monitor")
status_bar   = st.empty()
stats_section = st.empty()
plot_section = st.empty()


# ── Poll loop ─────────────────────────────────────────────────────────────────
def refresh():
    st.session_state.n_refreshes += 1

    # 1. Find latest file
    latest = find_latest_tdms(folder)
    if latest is None:
        st.session_state.error = f"No .tdms files found in: {folder}"
        return

    # 2. Hash check — skip if unchanged
    try:
        current_hash = file_md5(latest)
    except Exception as e:
        st.session_state.error = f"Cannot read {latest.name}: {e}"
        return

    if current_hash == st.session_state.last_hash and latest == st.session_state.last_path:
        return   # file unchanged — nothing to do

    # 3. Load new data
    try:
        df = load_str_channels(latest)
    except Exception as e:
        st.session_state.error = f"Error loading {latest.name}: {e}"
        return

    st.session_state.last_hash    = current_hash
    st.session_state.last_path    = latest
    st.session_state.df           = df
    st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
    st.session_state.error        = None


# Run one refresh cycle
refresh()

# ── Render ────────────────────────────────────────────────────────────────────
if st.session_state.error:
    status_bar.error(st.session_state.error)

elif st.session_state.df is not None:
    df   = st.session_state.df
    path = st.session_state.last_path

    # Status
    fs        = 1.0 / (df.index[1] - df.index[0]).total_seconds()
    duration  = (df.index[-1] - df.index[0]).total_seconds()
    status_bar.success(
        f"📄 **{path.name}**  |  "
        f"{len(df.columns)} STR channels  |  "
        f"{fs:.0f} Hz  |  "
        f"{duration:.1f} s  |  "
        f"Last updated: **{st.session_state.last_updated}**"
    )

    # Statistics table
    with stats_section.container():
        with st.expander("📊 Channel statistics (µε)", expanded=False):
            stats = df.describe().T[["mean", "std", "min", "max"]].round(3)
            stats.columns = ["mean (µε)", "std (µε)", "min (µε)", "max (µε)"]
            st.dataframe(stats, use_container_width=True)

    # Plot
    with plot_section.container():
        fig = build_figure(df)
        st.pyplot(fig)
        plt.close(fig)

else:
    status_bar.info("Waiting for data…")

# Sidebar session info
info_box.markdown(
    f"- Polls: **{st.session_state.n_refreshes}**\n"
    f"- File: `{Path(st.session_state.last_path).name if st.session_state.last_path else '—'}`\n"
    f"- Updated: `{st.session_state.last_updated or '—'}`"
)

# ── Auto-rerun every POLL_INTERVAL_S seconds ──────────────────────────────────
time.sleep(POLL_INTERVAL_S)
st.rerun()
