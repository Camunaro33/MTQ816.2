"""
Bridge STR Live Monitor — Streamlit App
========================================
- Watches a folder for the most-recent .tdms file
- Polls every 0.5 s only when a valid folder is set
- Does NOT poll if no folder / file is found
- Does NOT reload if the file has not changed
- Asks user to pick a folder if none is configured
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

STR_PREFIX      = "STR"
POLL_INTERVAL_S = 0.5

# ── Session-state initialisation ──────────────────────────────────────────────
_defaults = {
    "folder":        "",       # user-confirmed folder path
    "last_hash":     None,     # hash of last successfully read file
    "last_path":     None,     # Path of last successfully read file
    "df":            None,     # current DataFrame
    "last_updated":  None,
    "error":         None,
    "folder_error":  None,     # error specifically about folder/file finding
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_latest_tdms(folder: str) -> Path | None:
    files = glob.glob(os.path.join(folder, "**", "*.tdms"), recursive=True)
    if not files:
        files = glob.glob(os.path.join(folder, "*.tdms"))
    return Path(max(files, key=os.path.getmtime)) if files else None


def file_hash(path: Path) -> str:
    stat = path.stat()
    h = hashlib.md5((str(stat.st_mtime) + str(stat.st_size)).encode())
    with open(path, "rb") as f:
        h.update(f.read(65536))
        if stat.st_size > 65536:
            f.seek(-65536, 2)
            h.update(f.read())
    return h.hexdigest()


def load_str_channels(path: Path) -> pd.DataFrame:
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
        start=t0, periods=n,
        freq=pd.tseries.frequencies.to_offset(pd.Timedelta(seconds=increment)),
    )
    df = pd.DataFrame({ch.name: ch[:] for ch in channels}, index=index)
    df.index.name = "timestamp_utc"
    return df


def build_figure(df: pd.DataFrame) -> plt.Figure:
    cols   = df.columns.tolist()
    n      = len(cols)
    n_cols = 3
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(6 * n_cols, 3 * n_rows),
        sharex=True, constrained_layout=True,
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

    st.markdown("**Acquisition folder**")
    folder_input = st.text_input(
        "Folder path",
        value=st.session_state.folder,
        placeholder=r"e.g. D:\Sauvegarde\Manuelle",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns(2)
    with col1:
        confirm = st.button("✅ Set folder", use_container_width=True)
    with col2:
        clear = st.button("🗑 Clear", use_container_width=True)

    if confirm:
        folder_input = folder_input.strip()
        if os.path.isdir(folder_input):
            st.session_state.folder       = folder_input
            st.session_state.folder_error = None
            st.session_state.last_hash    = None   # force reload on new folder
            st.session_state.df           = None
        else:
            st.session_state.folder_error = f"Folder not found: '{folder_input}'"

    if clear:
        st.session_state.folder       = ""
        st.session_state.folder_error = None
        st.session_state.last_hash    = None
        st.session_state.last_path    = None
        st.session_state.df           = None
        st.session_state.last_updated = None
        st.session_state.error        = None

    if st.session_state.folder_error:
        st.error(st.session_state.folder_error)

    st.divider()
    st.caption(f"Polls every **{POLL_INTERVAL_S} s** — only when a folder is set and the file changes.")

    st.divider()
    st.markdown("**Session info**")
    info_placeholder = st.empty()


# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🌉 Bridge STR Live Monitor")
status_bar    = st.empty()
stats_section = st.empty()
plot_section  = st.empty()

folder = st.session_state.folder

# ── State machine ─────────────────────────────────────────────────────────────

# CASE 1 — No folder set yet: show instructions, stop, do NOT rerun
if not folder:
    status_bar.info(
        "👋 **No folder configured.**  \n"
        "Enter the path to your acquisition folder in the sidebar and click **✅ Set folder**."
    )
    with plot_section.container():
        st.markdown(
            """
            ### How to get started
            1. Type the folder path in the sidebar — e.g. `D:\\Sauvegarde\\Manuelle`
            2. Click **✅ Set folder**
            3. The app will find the most-recent `.tdms` file and start live monitoring
            """
        )
    # No st.rerun() — wait for user input
    st.stop()


# CASE 2 — Folder set, look for file
latest = find_latest_tdms(folder)

if latest is None:
    # CASE 2a — Folder exists but contains no .tdms file: show error, stop, do NOT rerun
    status_bar.warning(
        f"⚠️ No `.tdms` files found in `{folder}`.  \n"
        "Check the path in the sidebar or wait for the acquisition system to create a file."
    )
    # No st.rerun() — no point polling an empty folder continuously
    st.stop()


# CASE 3 — File found: check if it changed
try:
    current_hash = file_hash(latest)
except Exception as e:
    status_bar.error(f"Cannot read `{latest.name}`: {e}")
    st.stop()

file_changed = (
    current_hash != st.session_state.last_hash
    or latest != st.session_state.last_path
)

if file_changed:
    # CASE 3a — File is new or changed: load it
    try:
        df = load_str_channels(latest)
        st.session_state.last_hash    = current_hash
        st.session_state.last_path    = latest
        st.session_state.df           = df
        st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
        st.session_state.error        = None
    except Exception as e:
        st.session_state.error = str(e)

# CASE 3b — File unchanged: use cached df (nothing to reload)

# ── Render ────────────────────────────────────────────────────────────────────
if st.session_state.error:
    status_bar.error(f"Error loading data: {st.session_state.error}")

elif st.session_state.df is not None:
    df   = st.session_state.df
    path = st.session_state.last_path
    fs   = 1.0 / (df.index[1] - df.index[0]).total_seconds()
    dur  = (df.index[-1] - df.index[0]).total_seconds()

    badge = "🔄 **Updated**" if file_changed else "✅ **No change**"
    status_bar.success(
        f"{badge}  |  📄 `{path.name}`  |  "
        f"{len(df.columns)} STR ch.  |  {fs:.0f} Hz  |  {dur:.1f} s  |  "
        f"Last load: **{st.session_state.last_updated}**"
    )

    with stats_section.container():
        with st.expander("📊 Channel statistics (µε)", expanded=False):
            stats = df.describe().T[["mean", "std", "min", "max"]].round(3)
            stats.columns = ["mean (µε)", "std (µε)", "min (µε)", "max (µε)"]
            st.dataframe(stats, use_container_width=True)

    with plot_section.container():
        fig = build_figure(df)
        st.pyplot(fig)
        plt.close(fig)

# ── Sidebar info ──────────────────────────────────────────────────────────────
info_placeholder.markdown(
    f"- Folder: `{folder}`\n"
    f"- File: `{Path(st.session_state.last_path).name if st.session_state.last_path else '—'}`\n"
    f"- Updated: `{st.session_state.last_updated or '—'}`\n"
    f"- Changed: `{'yes' if file_changed else 'no'}`"
)

# ── Auto-rerun ONLY when a folder+file are active ─────────────────────────────
time.sleep(POLL_INTERVAL_S)
st.rerun()
