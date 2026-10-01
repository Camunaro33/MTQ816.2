import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Bridge STR Monitor", page_icon="🌉", layout="wide")

JSON_PATH    = Path(__file__).parent / "last_values.json"
# GitHub raw URL — app reads from here when running on Streamlit Cloud
GITHUB_RAW   = "https://raw.githubusercontent.com/Camunaro33/MTQ816.2/main/last_values.json"
POLL_S       = 0.5
HISTORY_SIZE = 400
BASELINE_MIN = 10   # wait at least N reads before accepting baseline

for k, v in {
    "last_ts": None, "last_values": None, "history": None,
    "n_reads": 0, "baseline": None, "baseline_buf": []
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════════════════
# SENSOR LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
L = 8120.0
X_D1 = 1075/L; X_MID = 0.5; X_D3 = (1075+2985+2985/2)/L

DECK = [
    ("STR_1_B8901","STR-01", 1-1075/L, 0.25, 90),
    ("STR_2_B8902","STR-02", 1-1075/L, 0.75, 90),
    ("STR_3_B8903","STR-03", 0.50,     0.25, 90),
    ("STR_4_B8904","STR-04", 0.50,     0.75, 90),
    ("STR_5_B8905","STR-05", X_D1+0.08,0.25,  0),
    ("STR_6_B8906","STR-06", X_D1+0.08,0.75,  0),
]
DECK_ZEROS = [
    (0,0),(0,.5),(0,1),(1,0),(1,.5),(1,1),
    (X_D1,0),(X_D1,1),(X_MID,0),(X_MID,1),(X_D3,0),(X_D3,1),
]

# Beam sensors — each beam has measurements at ONE x position (midspan area)
# top flange channels, bottom flange channels, x position
BEAMS = {
    "C": {
        "name": "Poutre C — Nord/Amont",
        "color": "#60a5fa",
        # Two measurement stations on Poutre C
        "stations": [
            {"x": X_D3,        "top": ["STR_7_B8907"],  "bot": ["STR_8_B8908"]},
            {"x": 1-1075/L,    "top": ["STR_9_B8909"],  "bot": ["STR_10_B8910"]},
        ]
    },
    "B": {
        "name": "Poutre B — Centre",
        "color": "#34d399",
        "stations": [
            {"x": X_MID-0.04,  "top": ["STR_13_B8913"], "bot": ["STR_14_B8914"]},
            {"x": X_MID+0.07,  "top": ["STR_11_B8911"], "bot": ["STR_12_B8912"]},
        ]
    },
    "A": {
        "name": "Poutre A — Sud/Aval",
        "color": "#f87171",
        "stations": [
            {"x": X_D1,        "top": ["STR_15_B8915"], "bot": ["STR_16_B8916"]},
            {"x": 1-1075/L,    "top": ["STR_17_B8917"], "bot": ["STR_18_B8918"]},
        ]
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def col_gr(t):
    t=max(0,min(1,t))
    return (int(255*t*2),210,30) if t<0.5 else (230,int(210*(1-(t-0.5)*2)),30)

def col_br(t):
    """t in [-1,1]: blue=compression, red=tension"""
    t=max(-1,min(1,t))
    if t<0: return int(220*(1+t)),int(220*(1+t)),220
    return 220,int(220*(1-t)),int(220*(1-t))

def tps_interp(pts, vs, gx, gy):
    pts=np.array(pts,dtype=float); vs=np.array(vs,dtype=float); n=len(pts)
    D=np.sqrt(((pts[:,None]-pts[None,:])**2).sum(2))
    K=np.where(D<1e-10,0,D**2*np.log(np.maximum(D,1e-10)))
    P=np.column_stack([np.ones(n),pts[:,0],pts[:,1]])
    A=np.block([[K,P],[P.T,np.zeros((3,3))]])
    b=np.concatenate([vs,[0,0,0]])
    w=np.linalg.lstsq(A,b,rcond=None)[0]
    GX,GY=np.meshgrid(gx,gy)
    gp=np.column_stack([GX.ravel(),GY.ravel()])
    d=np.sqrt(((gp[:,None]-pts[None,:])**2).sum(2))
    Kg=np.where(d<1e-10,0,d**2*np.log(np.maximum(d,1e-10)))
    Pg=np.column_stack([np.ones(len(gp)),gp[:,0],gp[:,1]])
    return (Kg@w[:n]+Pg@w[n:]).reshape(len(gy),len(gx))

def heatmap_rects(Z, x0,y0,W,H, absmax, blue_red=False):
    ny,nx=Z.shape; pw=W/nx; ph=H/ny; out=[]
    for j in range(ny):
        for i in range(nx):
            v=Z[j,i]
            if blue_red:
                r,g,b=col_br(v/max(absmax,1e-6))
            else:
                r,g,b=col_gr(abs(v)/max(absmax,1e-6))
            out.append(f'<rect x="{x0+i*pw:.1f}" y="{y0+j*ph:.1f}" '
                       f'width="{pw+0.6:.1f}" height="{ph+0.6:.1f}" '
                       f'fill="rgb({r},{g},{b})" opacity="0.9"/>')
    return "".join(out)

DEFS=('<defs>'
      '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
      '<path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>'
      '<marker id="ar2" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
      '<path d="M9 1L1 5L9 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>'
      '</defs>')

# ══════════════════════════════════════════════════════════════════════════════
# PLOT 1 — DECK CONTOUR
# ══════════════════════════════════════════════════════════════════════════════
def svg_deck(delta):
    W,H=820,310; DX,DY,DW,DH=80,55,680,175
    pts=list(DECK_ZEROS); vs=[0.0]*len(DECK_ZEROS)
    for ch,_,nx,ny,_ in DECK:
        v=delta.get(ch)
        if v is not None:
            pts.append((nx,ny)); vs.append(v)
    absmax=max((abs(v) for v in vs if v!=0),default=1.0)
    Z=tps_interp(pts,vs,np.linspace(0,1,90),np.linspace(0,1,30))

    s=[f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;font-family:sans-serif">',DEFS]
    s+=[f'<text x="{DX+DW//2}" y="20" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Aluminium deck plate — STR-01 to STR-06   (Δε from baseline)</text>',
        f'<text x="{DX+DW//2}" y="36" text-anchor="middle" font-size="10" fill="#777">Thin-plate spline · edges = 0 µε · zeroed at first stable reading</text>',
        heatmap_rects(Z,DX,DY,DW,DH,absmax),
        f'<rect x="{DX}" y="{DY}" width="{DW}" height="{DH}" rx="5" fill="none" stroke="#ccc" stroke-width="1.2"/>']
    for ny_,lbl in [(0,"Poutre C · Nord"),(0.5,"Poutre B"),(1,"Poutre A · Sud")]:
        sy_=DY+ny_*DH
        s+=[f'<line x1="{DX}" y1="{sy_:.0f}" x2="{DX+DW}" y2="{sy_:.0f}" stroke="#fff" stroke-width="1.8" opacity="0.4"/>',
            f'<text x="{DX-6}" y="{sy_+4:.0f}" text-anchor="end" font-size="8" fill="#888">{lbl}</text>']
    for nx_,lbl in [(0,"Aval"),(X_D1,"D1"),(0.5,"D2"),(X_D3,"D3"),(1,"Amont")]:
        sx_=DX+nx_*DW
        s+=[f'<line x1="{sx_:.0f}" y1="{DY}" x2="{sx_:.0f}" y2="{DY+DH}" stroke="#fff" stroke-width="0.7" opacity="0.2" stroke-dasharray="3 3"/>',
            f'<text x="{sx_:.0f}" y="{DY+DH+12}" text-anchor="middle" font-size="8" fill="#666">{lbl}</text>']
    s+=[f'<text x="{DX+5}" y="{DY-7}" font-size="9" fill="#aaa">← Côté aval (Mobile · Forêt)</text>',
        f'<text x="{DX+DW-5}" y="{DY-7}" text-anchor="end" font-size="9" fill="#aaa">(Fixé · Autoroute 175) Côté amont →</text>']
    for ch,label,nx_,ny_,angle in DECK:
        v=delta.get(ch); sx_=DX+nx_*DW; sy_=DY+ny_*DH
        txt=f"Δ{v:+.1f} µε" if v is not None else "N/A"; AR=18
        if angle==0:
            s.append(f'<line x1="{sx_-AR}" y1="{sy_:.0f}" x2="{sx_+AR}" y2="{sy_:.0f}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>')
        else:
            s.append(f'<line x1="{sx_:.0f}" y1="{sy_-AR}" x2="{sx_:.0f}" y2="{sy_+AR}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>')
        bw,bh=76,28; bx=sx_+22 if nx_<0.8 else sx_-22-bw; by=sy_-bh//2
        s+=[f'<rect x="{bx:.0f}" y="{by:.0f}" width="{bw}" height="{bh}" rx="4" fill="#0d1117" stroke="#fff" stroke-width="0.6" opacity="0.92"/>',
            f'<text x="{bx+bw//2:.0f}" y="{by+10:.0f}" text-anchor="middle" font-size="8" font-weight="bold" fill="#ccc">{label}</text>',
            f'<text x="{bx+bw//2:.0f}" y="{by+23:.0f}" text-anchor="middle" font-size="10" font-weight="bold" fill="white">{txt}</text>']

    # Colour bar
    steps=80; BAR_X,BAR_Y,BAR_W,BAR_H=DX,DY+DH+22,DW,11
    bar="".join(f'<rect x="{BAR_X+i*BAR_W/steps:.1f}" y="{BAR_Y}" width="{BAR_W/steps+0.5:.1f}" height="{BAR_H}" fill="rgb{col_gr(i/steps)}"/>' for i in range(steps))
    s+=[bar,f'<rect x="{BAR_X}" y="{BAR_Y}" width="{BAR_W}" height="{BAR_H}" fill="none" stroke="#555" stroke-width="0.8"/>',
        f'<text x="{BAR_X}" y="{BAR_Y+BAR_H+11}" font-size="9" fill="#888">0 µε</text>',
        f'<text x="{BAR_X+BAR_W//2}" y="{BAR_Y+BAR_H+11}" text-anchor="middle" font-size="9" fill="#888">|Δε| from baseline</text>',
        f'<text x="{BAR_X+BAR_W}" y="{BAR_Y+BAR_H+11}" text-anchor="end" font-size="9" fill="#888">{absmax:.1f} µε</text>']
    s.append('</svg>')
    return "".join(s)

# ══════════════════════════════════════════════════════════════════════════════
# PLOT 2 — BEAM ELEVATION CONTOUR (one per beam)
# For a simply-supported beam with sensors at known x positions:
#   - zero at x=0 (aval support) and x=1 (amont support)
#   - measured top & bottom flange Δε at sensor x positions
#   - interpolate in 2D: x=position along beam, y=cross-section (top=0, bot=1)
#   - contour shows bending strain distribution along the beam height
# ══════════════════════════════════════════════════════════════════════════════
def svg_one_beam(bk, delta, x0, y0, BW, BH):
    cfg=BEAMS[bk]; col=cfg["color"]; name=cfg["name"]

    # Build known points for TPS
    # Simply-supported → zero at both ends for ALL cross-section heights
    known_pts, known_vs = [], []
    for yy in np.linspace(0,1,5):
        known_pts.append((0.0, yy)); known_vs.append(0.0)  # aval support
        known_pts.append((1.0, yy)); known_vs.append(0.0)  # amont support

    # Sensor values — clamp outliers (>300 µε from median of same group = faulty channel)
    def safe_mean(chs):
        vs = [delta.get(c, 0) for c in chs]
        if len(vs) > 1:
            med = float(np.median(vs))
            vs  = [v for v in vs if abs(v - med) < 300]
        return float(np.mean(vs)) if vs else 0.0

    station_vals = []
    for st_ in cfg["stations"]:
        nx = st_["x"]
        tv = safe_mean(st_["top"])
        bv = safe_mean(st_["bot"])
        station_vals.append((nx, tv, bv))
        known_pts.append((nx, 0.0)); known_vs.append(tv)
        known_pts.append((nx, 1.0)); known_vs.append(bv)
        known_pts.append((nx, 0.5)); known_vs.append((tv+bv)/2)

    Z   = tps_interp(known_pts, known_vs, np.linspace(0,1,80), np.linspace(0,1,20))
    abm = max(abs(Z.max()), abs(Z.min()), 1.0)

    s=[]
    s.append(heatmap_rects(Z, x0,y0,BW,BH, abm, blue_red=True))
    s.append(f'<rect x="{x0}" y="{y0}" width="{BW}" height="{BH}" rx="4" fill="none" stroke="{col}" stroke-width="1.5"/>')
    s.append(f'<text x="{x0+BW//2}" y="{y0-8}" text-anchor="middle" font-size="10" font-weight="bold" fill="{col}">{name}</text>')
    s.append(f'<text x="{x0-4}" y="{y0+8}" text-anchor="end" font-size="8" fill="#666">top</text>')
    s.append(f'<text x="{x0-4}" y="{y0+BH}" text-anchor="end" font-size="8" fill="#666">bot</text>')

    # Support triangles
    for sx_ in [x0, x0+BW]:
        s.append(f'<polygon points="{sx_},{y0+BH} {sx_-8},{y0+BH+12} {sx_+8},{y0+BH+12}" fill="#888"/>')

    # Sensor dots ON the beam edges (top=y0, bot=y0+BH)
    for i, st_ in enumerate(cfg["stations"]):
        nx, tv, bv = station_vals[i][0], station_vals[i][1], station_vals[i][2]
        sx_ = x0 + nx*BW
        lbl_t = "+".join(c.split("_")[0]+"-"+c.split("_")[1] for c in st_["top"])
        lbl_b = "+".join(c.split("_")[0]+"-"+c.split("_")[1] for c in st_["bot"])
        # Top flange dot (sits on the top edge)
        s+=[f'<circle cx="{sx_:.0f}" cy="{y0}" r="10" fill="#0d1117" stroke="{col}" stroke-width="1.5"/>',
            f'<text x="{sx_:.0f}" y="{y0-2}" text-anchor="middle" font-size="7" font-weight="bold" fill="{col}">T</text>',
            f'<text x="{sx_:.0f}" y="{y0+8}" text-anchor="middle" font-size="8" fill="white">Δ{tv:+.0f}</text>',
            f'<text x="{sx_:.0f}" y="{y0-20}" text-anchor="middle" font-size="7" fill="#888">{lbl_t}</text>']
        # Bottom flange dot (sits on the bottom edge)
        s+=[f'<circle cx="{sx_:.0f}" cy="{y0+BH}" r="10" fill="#0d1117" stroke="{col}" stroke-width="1.5"/>',
            f'<text x="{sx_:.0f}" y="{y0+BH-2}" text-anchor="middle" font-size="7" font-weight="bold" fill="{col}">B</text>',
            f'<text x="{sx_:.0f}" y="{y0+BH+8}" text-anchor="middle" font-size="8" fill="white">Δ{bv:+.0f}</text>',
            f'<text x="{sx_:.0f}" y="{y0+BH+22}" text-anchor="middle" font-size="7" fill="#888">{lbl_b}</text>']

    # x-axis ticks
    for nx_,lbl in [(0,"Aval"),(X_D1,"D1"),(X_MID,"D2"),(X_D3,"D3"),(1,"Amont")]:
        sx_=x0+nx_*BW
        s+=[f'<line x1="{sx_:.0f}" y1="{y0+BH}" x2="{sx_:.0f}" y2="{y0+BH+5}" stroke="#555" stroke-width="0.8"/>',
            f'<text x="{sx_:.0f}" y="{y0+BH+16}" text-anchor="middle" font-size="8" fill="#555">{lbl}</text>']

    return "".join(s), abm

def svg_beams(delta):
    W,H=820,470; DX,DY,DW=75,40,680; BH=60; GAP=70
    s=[f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;font-family:sans-serif">',DEFS,
       f'<text x="{DX+DW//2}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Steel girders A · B · C — STR-07 to STR-18   (Δε from baseline)</text>',
       f'<text x="{DX+DW//2}" y="32" text-anchor="middle" font-size="10" fill="#777">Simply-supported beam · top→bottom cross-section · blue = compression · red = tension</text>']

    all_abs=1.0
    for i,bk in enumerate(["C","B","A"]):
        y0=DY+28+i*(BH+GAP)
        bsvg,abm=svg_one_beam(bk,delta,DX,y0,DW,BH)
        s.append(bsvg); all_abs=max(all_abs,abm)

    # Shared colour bar
    bar_y=DY+28+3*(BH+GAP)-GAP+35
    steps=80; BAR_W=DW; BAR_H=11
    bar="".join(f'<rect x="{DX+i*BAR_W/steps:.1f}" y="{bar_y}" width="{BAR_W/steps+0.5:.1f}" height="{BAR_H}" fill="rgb{col_br((i/steps)*2-1)}"/>' for i in range(steps))
    s+=[bar,f'<rect x="{DX}" y="{bar_y}" width="{BAR_W}" height="{BAR_H}" fill="none" stroke="#555" stroke-width="0.8"/>',
        f'<text x="{DX}" y="{bar_y+BAR_H+11}" font-size="9" fill="#6af">{-all_abs:.1f} µε (compression)</text>',
        f'<text x="{DX+BAR_W//2}" y="{bar_y+BAR_H+11}" text-anchor="middle" font-size="9" fill="#aaa">0 µε</text>',
        f'<text x="{DX+BAR_W}" y="{bar_y+BAR_H+11}" text-anchor="end" font-size="9" fill="#f87">{all_abs:.1f} µε (tension)</text>']
    s.append('</svg>')
    return "".join(s)

def update_history(delta):
    row=pd.DataFrame([delta],index=[pd.Timestamp.now(tz="UTC")])
    hist=st.session_state.history
    hist=pd.concat([hist,row]).tail(HISTORY_SIZE) if hist is not None else row
    st.session_state.history=hist

# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT — stable rendering (no postMessage, no iframe tricks)
# Scroll position preserved by using st.empty() placeholders defined ONCE
# at the top, and only updating their content — Streamlit does not re-scroll
# when only placeholder content changes.
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🌉 Bridge STR Monitor")
    st.divider()
    st.markdown(
        "All values are **Δε from baseline**.\n\n"
        f"Baseline locked after **{BASELINE_MIN} stable reads** "
        "(or click Reset to re-zero now)."
    )
    if st.button("🔄 Reset baseline"):
        st.session_state.baseline    = None
        st.session_state.baseline_buf= []
        st.session_state.history     = None
        st.session_state.n_reads     = 0
    st.divider()
    info_ph = st.empty()

st.title("🌉 Bridge — Live Strain Monitor")
status_bar = st.empty()

# These placeholders are created ONCE — updating them never scrolls the page
deck_ph  = st.empty()
beam_ph  = st.empty()
hist_ph  = st.empty()

# Prevent scroll-to-top by injecting CSS that anchors the page
components.html(
    "<script>window.parent.document.documentElement.style.scrollBehavior='auto';</script>",
    height=0
)

# ── Read & process data ───────────────────────────────────────────────────────
import urllib.request

data = None
# Try local file first (acquisition PC), then GitHub (Streamlit Cloud / remote viewers)
if JSON_PATH.exists():
    try: data = json.loads(JSON_PATH.read_text())
    except: pass

if data is None:
    try:
        with urllib.request.urlopen(GITHUB_RAW, timeout=4) as r:
            data = json.loads(r.read().decode())
    except:
        pass

if data is None:
    status_bar.warning(
        "⏳ Waiting for data…\n\n"
        "Make sure `reader.py` is running on the acquisition PC "
        "and `GITHUB_TOKEN` is configured."
    )
    info_ph.markdown("- Status: waiting")
    time.sleep(POLL_S); st.rerun()

ts      = data["ts"]
changed = ts != st.session_state.last_ts

if changed:
    raw = data["values"]
    st.session_state.last_ts = ts
    st.session_state.n_reads += 1

    # Accumulate baseline buffer
    buf = st.session_state.baseline_buf
    buf.append(dict(raw))
    if len(buf) > BASELINE_MIN:
        buf.pop(0)
    st.session_state.baseline_buf = buf

    # Lock baseline once we have enough stable reads
    if st.session_state.baseline is None and len(buf) >= BASELINE_MIN:
        # Use median of buffer to be robust to transients
        st.session_state.baseline = {
            ch: float(np.median([r.get(ch,0) for r in buf]))
            for ch in raw
        }

    baseline = st.session_state.baseline
    if baseline:
        delta = {ch: raw.get(ch,0) - baseline.get(ch,0) for ch in raw}
    else:
        delta = {ch: 0.0 for ch in raw}

    st.session_state.last_values = delta
    update_history(delta)

delta = st.session_state.last_values or {}
badge = "🔄 Updated" if changed else "✅ No change"
bl_status = f"✅ locked ({BASELINE_MIN} reads)" if st.session_state.baseline else f"⏳ buffering ({len(st.session_state.baseline_buf)}/{BASELINE_MIN})"

status_bar.success(
    f"**{badge}** | 📄 `{data['file']}` | "
    f"reads: **{st.session_state.n_reads}** | {data['ts'][11:19]} UTC | "
    f"baseline: {bl_status}"
)

# Render into placeholders — no page jump
with deck_ph.container():
    components.html(
        f'<div style="background:#0d1117;padding:12px;border-radius:10px">{svg_deck(delta)}</div>',
        height=355, scrolling=False
    )

with beam_ph.container():
    components.html(
        f'<div style="background:#0d1117;padding:12px;border-radius:10px">{svg_beams(delta)}</div>',
        height=520, scrolling=False
    )

if st.session_state.history is not None and len(st.session_state.history) > 1:
    with hist_ph.container():
        with st.expander("📈 History", expanded=False):
            t1,t2=st.tabs(["Deck STR-01..06","Girders STR-07..18"])
            with t1:
                cols=[s[0] for s in DECK if s[0] in st.session_state.history.columns]
                if cols: st.line_chart(st.session_state.history[cols], height=180)
            with t2:
                all_g=[c for g in BEAMS.values() for st_ in g["stations"] for c in st_["top"]+st_["bot"]]
                cols=[c for c in all_g if c in st.session_state.history.columns]
                if cols: st.line_chart(st.session_state.history[cols], height=180)

info_ph.markdown(
    f"- File: `{data['file']}`\n"
    f"- Reads: `{st.session_state.n_reads}`\n"
    f"- Baseline: {bl_status}"
)

time.sleep(POLL_S)
st.rerun()
