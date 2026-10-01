"""
Bridge STR Live Monitor — Streamlit App
========================================
Two modes:
  1. LOCAL  — type a folder path → watches for newest .tdms, polls every 0.5 s
  2. CLOUD  — upload a .tdms file manually via the file-uploader widget

Rules:
  - If folder is not found → show error, stop, do NOT rerun
  - If no .tdms in folder  → show warning, stop, do NOT rerun
  - If file unchanged      → use cached data, do NOT reload
  - Only rerun (poll) when a valid folder+file are active
"""

import os
import io
import time
import glob
import hashlib
import tempfile
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

# ── Session state ─────────────────────────────────────────────────────────────
_defaults = {
    "folder":        "",
    "last_hash":     None,
    "last_path":     None,
    "df":            None,
    "last_updated":  None,
    "error":         None,
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


def bytes_hash(data: bytes) -> str:
    return hashlib.md5(data[:65536] + data[-65536:] if len(data) > 131072 else data).hexdigest()


def load_str_from_path(path: Path) -> pd.DataFrame:
    tf = TdmsFile.read(str(path))
    return _extract_str(tf, path.name)


def load_str_from_bytes(data: bytes, name: str) -> pd.DataFrame:
    with tempfile.NamedTemporaryFile(suffix=".tdms", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        tf = TdmsFile.read(str(tmp_path))
        return _extract_str(tf, name)
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_str(tf: TdmsFile, filename: str) -> pd.DataFrame:
    channels = [
        ch
        for group in tf.groups()
        for ch in group.channels()
        if ch.name.upper().startswith(STR_PREFIX)
    ]
    if not channels:
        raise ValueError(f"No '{STR_PREFIX}*' channels found in {filename}.")
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


def render_data(df, filename, file_changed):
    fs  = 1.0 / (df.index[1] - df.index[0]).total_seconds()
    dur = (df.index[-1] - df.index[0]).total_seconds()
    badge = "🔄 **Updated**" if file_changed else "✅ **No change**"
    status_bar.success(
        f"{badge}  |  📄 `{filename}`  |  "
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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌉 Bridge STR Monitor")

    mode = st.radio(
        "Mode",
        ["📁 Local folder (live)", "☁️ Upload file (manual)"],
        index=0,
    )

    st.divider()

    if mode == "📁 Local folder (live)":
        st.markdown("**Acquisition folder**")
        st.caption("Paste the full path to the folder that contains your `.tdms` files.")
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
            clear   = st.button("🗑 Clear", use_container_width=True)

        if confirm:
            f = folder_input.strip()
            if os.path.isdir(f):
                if f != st.session_state.folder:
                    st.session_state.last_hash = None   # force reload
                    st.session_state.df        = None
                st.session_state.folder = f
                st.session_state.error  = None
            else:
                st.session_state.error = (
                    f"❌ Folder not found: `{f}`\n\n"
                    "Make sure:\n"
                    "- The path is correct\n"
                    "- You are running the app **locally** on the PC that has this drive\n"
                    "- The drive letter / mount is accessible"
                )

        if clear:
            for k in ("folder", "last_hash", "last_path", "df", "last_updated", "error"):
                st.session_state[k] = _defaults[k]

        if st.session_state.error:
            st.error(st.session_state.error)

        st.divider()
        st.caption(f"Polls every **{POLL_INTERVAL_S} s**. Reloads only when the file changes.")

    else:
        st.markdown("**Upload a `.tdms` file**")
        uploaded = st.file_uploader(
            "Drop your TDMS file here",
            type=["tdms"],
            label_visibility="collapsed",
        )
        st.caption("Upload a new file to refresh the plot.")

    st.divider()
    st.markdown("**Session info**")
    info_ph = st.empty()


# ── Main layout ───────────────────────────────────────────────────────────────
st.title("🌉 Bridge STR Live Monitor")
status_bar    = st.empty()
stats_section = st.empty()
plot_section  = st.empty()

should_rerun = False   # set True only in live-folder mode with a valid file

# ══════════════════════════════════════════════════════════════════════════════
# MODE A — Upload
# ══════════════════════════════════════════════════════════════════════════════
if mode == "☁️ Upload file (manual)":
    if "uploaded" not in dir() or uploaded is None:
        status_bar.info(
            "☁️ **Upload mode** — use the sidebar to upload a `.tdms` file."
        )
        info_ph.markdown("- Mode: upload\n- File: —")
        st.stop()

    raw  = uploaded.read()
    h    = bytes_hash(raw)
    changed = h != st.session_state.last_hash

    if changed:
        try:
            df = load_str_from_bytes(raw, uploaded.name)
            st.session_state.last_hash    = h
            st.session_state.last_path    = Path(uploaded.name)
            st.session_state.df           = df
            st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
            st.session_state.error        = None
        except Exception as e:
            status_bar.error(str(e))
            st.stop()

    if st.session_state.df is not None:
        render_data(st.session_state.df, uploaded.name, changed)

    info_ph.markdown(
        f"- Mode: upload\n"
        f"- File: `{uploaded.name}`\n"
        f"- Updated: `{st.session_state.last_updated or '—'}`"
    )
    st.stop()   # no auto-rerun in upload mode

# ══════════════════════════════════════════════════════════════════════════════
# MODE B — Local folder (live)
# ══════════════════════════════════════════════════════════════════════════════
folder = st.session_state.folder

if not folder:
    status_bar.info(
        "👋 **No folder configured.**  \n"
        "Enter the path to your acquisition folder in the sidebar and click **✅ Set folder**."
    )
    with plot_section.container():
        st.markdown(
            """
            ### How to get started
            1. Make sure you are running this app **locally** on the acquisition PC:
               ```
               pip install -r requirements.txt
               streamlit run app.py
               ```
            2. Type the folder path in the sidebar — e.g. `D:\\Sauvegarde\\Manuelle`
            3. Click **✅ Set folder**
            4. The app finds the most-recent `.tdms` file and starts live monitoring

            > ⚠️ If you are using **Streamlit Cloud**, switch to **☁️ Upload file** mode in the sidebar.
            """
        )
    info_ph.markdown("- Mode: local\n- Folder: —")
    st.stop()   # wait for user — no rerun

# Folder is set — check it still exists
if not os.path.isdir(folder):
    status_bar.error(
        f"❌ Folder no longer accessible: `{folder}`  \n"
        "Check that the drive is mounted and the path is correct."
    )
    info_ph.markdown(f"- Mode: local\n- Folder: `{folder}` ❌")
    st.stop()   # do NOT rerun — no point looping on a missing drive

# Find latest file
latest = find_latest_tdms(folder)
if latest is None:
    status_bar.warning(
        f"⚠️ No `.tdms` files found in `{folder}`.  \n"
        "Waiting for the acquisition system to create a file…"
    )
    info_ph.markdown(f"- Mode: local\n- Folder: `{folder}` ✅\n- File: none yet")
    st.stop()   # do NOT rerun — nothing to poll

# File found — hash check
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
    try:
        df = load_str_from_path(latest)
        st.session_state.last_hash    = current_hash
        st.session_state.last_path    = latest
        st.session_state.df           = df
        st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
        st.session_state.error        = None
    except Exception as e:
        status_bar.error(f"Error loading `{latest.name}`: {e}")
        st.stop()

if st.session_state.df is not None:
    render_data(st.session_state.df, latest.name, file_changed)

info_ph.markdown(
    f"- Mode: local\n"
    f"- Folder: `{folder}`\n"
    f"- File: `{latest.name}`\n"
    f"- Updated: `{st.session_state.last_updated or '—'}`\n"
    f"- Changed: {'yes 🔄' if file_changed else 'no ✅'}"
)

# Auto-rerun ONLY here (valid folder + file found)
should_rerun = True

if should_rerun:
    time.sleep(POLL_INTERVAL_S)
    st.rerun()
