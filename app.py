"""
Bridge STR Live Monitor — Streamlit App
========================================
Reads the LAST VALUE of each STR channel every 0.5 s.

Key behaviours:
  - Handles files being actively written by LabVIEW (incomplete last segment)
  - Copies file to a temp location before reading to avoid I/O race conditions
  - Suppresses nptdms warnings about partial segments (normal during acquisition)
  - Does NOT reload when file hash is unchanged
  - Does NOT poll when no folder / file is found
  - Keeps a rolling sparkline history of the last 200 reads (~100 s)

Modes:
  📁 Local folder (live) — run on the acquisition PC, auto-polls every 0.5 s
  ☁️ Upload file (manual) — use on Streamlit Cloud, manual upload
"""

import os
import io
import time
import glob
import shutil
import hashlib
import tempfile
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import streamlit as st
from nptdms import TdmsFile

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bridge STR Monitor", page_icon="🌉", layout="wide")

STR_PREFIX      = "STR"
POLL_INTERVAL_S = 0.5
HISTORY_SIZE    = 200   # number of 0.5 s ticks to keep (~100 s)

# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "folder":        "",
    "last_hash":     None,
    "last_path":     None,
    "last_values":   None,
    "history":       None,
    "last_updated":  None,
    "n_reads":       0,
    "error":         None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Core reader ────────────────────────────────────────────────────────────────

def _read_last_from_path(tdms_path: str) -> dict:
    """
    Read the last value of every STR channel from a TDMS file path.

    Uses TdmsFile.open() (streaming / lazy) which:
      - Reads metadata first, data on demand  →  fast for last-value access
      - Recovers from incomplete last segments (file still being written)
      - Handles chunk-size mismatches silently

    All nptdms warnings are suppressed — they are expected during live acquisition.
    """
    result = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with TdmsFile.open(tdms_path) as tf:
            for group in tf.groups():
                for ch in group.channels():
                    if ch.name.upper().startswith(STR_PREFIX):
                        try:
                            # ch[-1] triggers a minimal data read (last chunk only)
                            result[ch.name] = float(ch[-1])
                        except Exception:
                            pass   # channel exists but has no data yet
    return result


def read_last_values_from_file(path: Path) -> dict:
    """
    Safely read a TDMS file that may be actively written by LabVIEW.

    Strategy: copy the file (and its index if present) to a temp directory
    before reading.  This avoids I/O race conditions where LabVIEW is writing
    a new segment while we are reading — without this, nptdms can hit an
    unexpected EOF mid-segment and raise an exception.

    The copy is cheap (OS-level, same disk) and takes < 5 ms for typical files.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tdms = os.path.join(tmpdir, path.name)
        shutil.copy2(str(path), tmp_tdms)

        # Also copy the index file if it exists — nptdms prefers it
        index_path = path.with_suffix(".tdms_index")
        if index_path.exists():
            shutil.copy2(str(index_path), os.path.join(tmpdir, index_path.name))

        vals = _read_last_from_path(tmp_tdms)

    if not vals:
        raise ValueError(f"No '{STR_PREFIX}*' channels found in {path.name}.")
    return vals


def read_last_values_from_bytes(data: bytes, name: str) -> dict:
    """Same as above but for an in-memory upload (Streamlit uploader)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tdms = os.path.join(tmpdir, name if name.endswith(".tdms") else name + ".tdms")
        with open(tmp_tdms, "wb") as f:
            f.write(data)
        vals = _read_last_from_path(tmp_tdms)

    if not vals:
        raise ValueError(f"No '{STR_PREFIX}*' channels found in {name}.")
    return vals


# ── File helpers ───────────────────────────────────────────────────────────────

def find_latest_tdms(folder: str) -> Path | None:
    files = glob.glob(os.path.join(folder, "**", "*.tdms"), recursive=True)
    if not files:
        files = glob.glob(os.path.join(folder, "*.tdms"))
    return Path(max(files, key=os.path.getmtime)) if files else None


def file_hash(path: Path) -> str:
    """Fast hash using mtime + size — no file content read needed."""
    stat = path.stat()
    return hashlib.md5(
        (str(stat.st_mtime) + str(stat.st_size)).encode()
    ).hexdigest()


def bytes_hash(data: bytes) -> str:
    sample = data[:65536] + (data[-65536:] if len(data) > 131072 else b"")
    return hashlib.md5(sample).hexdigest()


# ── History ────────────────────────────────────────────────────────────────────

def update_history(vals: dict) -> pd.DataFrame:
    row  = pd.DataFrame([vals], index=[pd.Timestamp.now(tz="UTC")])
    hist = st.session_state.history
    hist = pd.concat([hist, row]).tail(HISTORY_SIZE) if hist is not None else row
    st.session_state.history = hist
    return hist


# ── Dashboard figure ───────────────────────────────────────────────────────────

def build_dashboard(vals: dict, hist: pd.DataFrame, filename: str) -> plt.Figure:
    channels = list(vals.keys())
    n        = len(channels)
    n_cols   = 6
    n_rows   = (n + n_cols - 1) // n_cols

    fig = plt.figure(figsize=(18, 3 * n_rows + 4), facecolor="#0e1117")

    all_v = np.array(list(vals.values()))
    med   = np.median(all_v)
    span  = max(np.abs(all_v - med).max(), 1.0)

    gs_top = gridspec.GridSpec(
        n_rows, n_cols, figure=fig,
        top=0.97, bottom=0.38, hspace=0.5, wspace=0.35,
    )
    gs_bot = gridspec.GridSpec(1, 1, figure=fig, top=0.30, bottom=0.05)

    # ── Value cards
    for i, ch in enumerate(channels):
        v    = vals[ch]
        norm = min(abs(v - med) / span, 1.0)
        col  = (norm, 1.0 - norm * 0.7, 0.2)   # green → red

        ax = fig.add_subplot(gs_top[i // n_cols, i % n_cols])
        ax.set_facecolor("#1c1e26")
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor("#333")

        ax.text(0.5, 0.72,
                ch.replace("_", "\n", 1),
                ha="center", va="center", fontsize=7,
                color="#aaaaaa", transform=ax.transAxes,
                fontfamily="monospace")
        ax.text(0.5, 0.28,
                f"{v:+.1f} µε",
                ha="center", va="center", fontsize=11, fontweight="bold",
                color=col, transform=ax.transAxes)

    for i in range(n, n_rows * n_cols):
        fig.add_subplot(gs_top[i // n_cols, i % n_cols]).set_visible(False)

    # ── Sparklines
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
        f"Last {len(hist)} reads  ({elapsed:.0f} s)  —  {filename}  "
        f"@ {datetime.now().strftime('%H:%M:%S')}",
        color="#cccccc", fontsize=9, loc="left",
    )

    cmap = plt.cm.tab20
    for j, ch in enumerate(channels):
        if ch in hist.columns:
            ax_bot.plot(
                hist.index, hist[ch],
                linewidth=0.9,
                color=cmap(j / max(n - 1, 1)),
                label=ch,
                alpha=0.85,
            )
    ax_bot.legend(
        fontsize=6, ncol=6, loc="upper left",
        labelcolor="#cccccc", facecolor="#1c1e26",
        edgecolor="#333", framealpha=0.7,
    )
    ax_bot.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M:%S"))
    ax_bot.tick_params(axis="x", rotation=20, labelsize=7)
    fig.patch.set_facecolor("#0e1117")
    return fig


# ── Render helper ──────────────────────────────────────────────────────────────

def render(vals, filename, file_changed, status_bar, plot_area):
    badge = "🔄 Updated" if file_changed else "✅ No change"
    status_bar.success(
        f"**{badge}**  |  📄 `{filename}`  |  "
        f"reads: **{st.session_state.n_reads}**  |  "
        f"last: **{st.session_state.last_updated}**"
    )
    with plot_area.container():
        fig = build_dashboard(vals, st.session_state.history, filename)
        st.pyplot(fig)
        plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🌉 Bridge STR Monitor")

    mode = st.radio("Mode", ["📁 Local folder (live)", "☁️ Upload file (manual)"])
    st.divider()

    uploaded = None

    if mode == "📁 Local folder (live)":
        st.markdown("**Acquisition folder**")
        folder_input = st.text_input(
            "path", value=st.session_state.folder,
            placeholder=r"D:\Sauvegarde\Manuelle",
            label_visibility="collapsed",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Set", use_container_width=True):
                f = folder_input.strip()
                if os.path.isdir(f):
                    if f != st.session_state.folder:
                        st.session_state.last_hash = None
                        st.session_state.history   = None
                    st.session_state.folder = f
                    st.session_state.error  = None
                else:
                    st.session_state.error = (
                        f"❌ Not found: `{f}`\n\n"
                        "Run the app **locally** on the acquisition PC.\n\n"
                        "On Streamlit Cloud → switch to **☁️ Upload file** mode."
                    )
        with c2:
            if st.button("🗑 Clear", use_container_width=True):
                for k, v in _defaults.items():
                    st.session_state[k] = v

        if st.session_state.error:
            st.error(st.session_state.error)

        st.caption(
            f"Polls every **{POLL_INTERVAL_S} s**.\n"
            "Reads only the **last sample** of each channel.\n"
            "File is copied before reading to handle live writes safely."
        )

    else:
        st.markdown("**Upload a `.tdms` file**")
        uploaded = st.file_uploader(
            "drop", type=["tdms"], label_visibility="collapsed"
        )
        st.caption(
            "Works with files currently being written by LabVIEW.\n"
            "Upload a new version to refresh."
        )

    st.divider()
    st.markdown("**Live info**")
    info_ph = st.empty()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
st.title("🌉 Bridge STR Live Monitor")
status_bar = st.empty()
plot_area  = st.empty()

# ── UPLOAD MODE ───────────────────────────────────────────────────────────────
if mode == "☁️ Upload file (manual)":
    if uploaded is None:
        status_bar.info(
            "☁️ **Upload mode** — drop a `.tdms` file in the sidebar.\n\n"
            "Works with files that are still being written by LabVIEW."
        )
        info_ph.markdown("- Mode: upload\n- File: —")
        st.stop()   # no rerun — wait for upload

    raw     = uploaded.read()
    h       = bytes_hash(raw)
    changed = h != st.session_state.last_hash

    if changed:
        try:
            vals = read_last_values_from_bytes(raw, uploaded.name)
            st.session_state.last_hash    = h
            st.session_state.last_path    = Path(uploaded.name)
            st.session_state.last_values  = vals
            st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
            st.session_state.n_reads     += 1
            st.session_state.error        = None
            update_history(vals)
        except Exception as e:
            status_bar.error(f"❌ {e}")
            st.stop()

    if st.session_state.last_values:
        render(st.session_state.last_values, uploaded.name, changed, status_bar, plot_area)

    info_ph.markdown(
        f"- Mode: upload\n"
        f"- File: `{uploaded.name}`\n"
        f"- Reads: `{st.session_state.n_reads}`\n"
        f"- Updated: `{st.session_state.last_updated or '—'}`"
    )
    st.stop()   # no auto-rerun in upload mode


# ── LOCAL FOLDER MODE ─────────────────────────────────────────────────────────
folder = st.session_state.folder

if not folder:
    status_bar.info(
        "👋 **No folder configured.**\n\n"
        "Enter the acquisition folder path in the sidebar and click **✅ Set**.\n\n"
        "> On Streamlit Cloud, switch to **☁️ Upload file** mode."
    )
    st.stop()   # no rerun

if not os.path.isdir(folder):
    status_bar.error(f"❌ Folder not accessible: `{folder}`")
    info_ph.markdown(f"- Folder: ❌\n- `{folder}`")
    st.stop()   # no rerun — drive may be disconnected

latest = find_latest_tdms(folder)
if latest is None:
    status_bar.warning(f"⚠️ No `.tdms` files found in `{folder}` — waiting for acquisition to start…")
    info_ph.markdown(f"- Folder: ✅ `{folder}`\n- File: none yet")
    st.stop()   # no rerun — nothing to poll

# Hash check (mtime + size only — no file read)
try:
    current_hash = file_hash(latest)
except Exception as e:
    status_bar.error(f"Cannot stat `{latest.name}`: {e}")
    st.stop()

file_changed = (
    current_hash != st.session_state.last_hash
    or latest     != st.session_state.last_path
)

if file_changed:
    try:
        # Copy then read — safe even if LabVIEW is writing at this exact moment
        vals = read_last_values_from_file(latest)
        st.session_state.last_hash    = current_hash
        st.session_state.last_path    = latest
        st.session_state.last_values  = vals
        st.session_state.last_updated = datetime.now().strftime("%H:%M:%S")
        st.session_state.n_reads     += 1
        st.session_state.error        = None
        update_history(vals)
    except Exception as e:
        # Don't crash — keep showing last good values, log the error
        status_bar.warning(
            f"⚠️ Read failed (file may be mid-write): `{e}` — retrying next poll…"
        )
        # Still rerun so we retry in 0.5 s
        time.sleep(POLL_INTERVAL_S)
        st.rerun()

if st.session_state.last_values:
    render(st.session_state.last_values, latest.name, file_changed, status_bar, plot_area)
else:
    status_bar.info("⏳ Waiting for first successful read…")

info_ph.markdown(
    f"- Mode: local\n"
    f"- File: `{latest.name}`\n"
    f"- Reads: `{st.session_state.n_reads}`\n"
    f"- Updated: `{st.session_state.last_updated or '—'}`\n"
    f"- Changed: {'🔄 yes' if file_changed else '✅ no'}"
)

# ── Auto-rerun (only in live folder mode with a valid file) ───────────────────
time.sleep(POLL_INTERVAL_S)
st.rerun()
