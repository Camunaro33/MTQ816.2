"""
app.py — Bridge STR Live Monitor
Serves a single HTML page that polls GitHub for last_values.json every 500ms.
No Streamlit rerun = no flash, no scroll jump, no flicker.
"""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Bridge STR Monitor", page_icon="🌉", layout="wide")

GITHUB_RAW = "https://raw.githubusercontent.com/Camunaro33/MTQ816.2/main/last_values.json"

# ── Sensor config passed to JS ─────────────────────────────────────────────────
# All layout/interpolation done in JavaScript — no Python rerun needed

HTML = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0d1117; font-family: sans-serif; color: #ccc; padding: 8px; }}
#status {{ font-size: 11px; color: #556; padding: 4px 0 8px 0; font-family: monospace; }}
h2 {{ font-size: 13px; font-weight: bold; text-align: center; margin: 6px 0 2px; }}
h3 {{ font-size: 12px; font-weight: bold; }}
p.sub {{ font-size: 10px; color: #666; text-align: center; margin-bottom: 6px; }}
.panel {{ background: #0d1117; border-radius: 8px; margin-bottom: 12px; }}
svg {{ width: 100%; display: block; }}
.tab {{
  background: #1c2333; border: 1px solid #333; color: #aaa;
  padding: 6px 14px; border-radius: 6px; cursor: pointer;
  font-size: 12px; font-family: sans-serif; transition: all 0.15s;
}}
.tab:hover {{ background: #253048; color: #eee; }}
.tab.active {{ background: #2563eb; border-color: #2563eb; color: #fff; font-weight: bold; }}
</style>
</head>
<body>
<div id="status">Connecting…</div>

<!-- Tab buttons -->
<div id="tabs" style="display:flex;gap:6px;margin-bottom:10px">
  <button onclick="showTab(0)" id="tab0" class="tab active">🏗 Deck (STR-01–06)</button>
  <button onclick="showTab(1)" id="tab1" class="tab">🔩 Beams (STR-07–18)</button>
  <button onclick="showTab(2)" id="tab2" class="tab">📐 Deflection</button>
  <button onclick="showTab(3)" id="tab3" class="tab">📈 History</button>
</div>

<!-- Tab panels -->
<div class="panel tab-panel" id="panel0"><div id="deck-panel"></div></div>
<div class="panel tab-panel" id="panel1" style="display:none"><div id="beam-panel"></div></div>
<div class="panel tab-panel" id="panel2" style="display:none"><div id="deflection-panel"></div></div>
<div class="panel tab-panel" id="panel3" style="display:none">
  <div style="padding:8px">
    <h3 style="color:#eee;font-size:12px;margin-bottom:6px">📈 Deck sensors — STR-01 to STR-06 (Δε from baseline)</h3>
    <canvas id="chart-deck" height="180"></canvas>
    <h3 style="color:#eee;font-size:12px;margin:12px 0 6px">📈 Beam sensors — STR-07 to STR-18 (Δε from baseline)</h3>
    <canvas id="chart-beams" height="180"></canvas>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const GITHUB_RAW = "{GITHUB_RAW}";
const L = 8120;
const X_D1 = 1075/L, X_MID = 0.5, X_D3 = (1075+2985+2985/2)/L;

// ── Sensor layout ──────────────────────────────────────────────────────────────
const DECK = [
  {{ch:"STR_1_B8901", label:"STR-01", nx:1-1075/L, ny:0.25, angle:90}},
  {{ch:"STR_2_B8902", label:"STR-02", nx:1-1075/L, ny:0.75, angle:90}},
  {{ch:"STR_3_B8903", label:"STR-03", nx:0.50,     ny:0.25, angle:90}},
  {{ch:"STR_4_B8904", label:"STR-04", nx:0.50,     ny:0.75, angle:90}},
  {{ch:"STR_5_B8905", label:"STR-05", nx:X_D1+0.08,ny:0.25, angle:0}},
  {{ch:"STR_6_B8906", label:"STR-06", nx:X_D1+0.08,ny:0.75, angle:0}},
];
const DECK_ZEROS = [
  [0,0],[0,.5],[0,1],[1,0],[1,.5],[1,1],
  [X_D1,0],[X_D1,1],[X_MID,0],[X_MID,1],[X_D3,0],[X_D3,1],
];
// ALL sensors are at MIDSPAN cross-section
// Each beam: 2 top flange gauges + 2 bottom flange gauges
// Poutre A (Voie A): top=STR-15,17  bot=STR-16,18
// Poutre B (Voie B): top=STR-11,13  bot=STR-12,14
// Poutre C (Voie C): top=STR-07,09  bot=STR-08,10
const BEAMS = [
  {{key:"C", name:"Poutre C — Nord/Amont (Voie C)", color:"#60a5fa",
    top:["STR_7_B8907","STR_9_B8909"], bot:["STR_8_B8908","STR_10_B8910"],
    topLabel:"STR-07, STR-09", botLabel:"STR-08, STR-10"}},
  {{key:"B", name:"Poutre B — Centre (Voie B)", color:"#34d399",
    top:["STR_11_B8911","STR_13_B8913"], bot:["STR_12_B8912","STR_14_B8914"],
    topLabel:"STR-11, STR-13", botLabel:"STR-12, STR-14"}},
  {{key:"A", name:"Poutre A — Sud/Aval (Voie A)", color:"#f87171",
    top:["STR_15_B8915","STR_17_B8917"], bot:["STR_16_B8916","STR_18_B8918"],
    topLabel:"STR-15, STR-17", botLabel:"STR-16, STR-18"}},
];

// ── Baseline management ────────────────────────────────────────────────────────
let baseline = null;
let baselineBuf = [];
const BASELINE_MIN = 10;

// ── Colour functions ───────────────────────────────────────────────────────────
function colGR(t) {{
  t = Math.max(0, Math.min(1, t));
  if (t < 0.5) return `rgb(${{Math.round(255*t*2)}},210,30)`;
  return `rgb(230,${{Math.round(210*(1-(t-0.5)*2))}},30)`;
}}
function colBR(t) {{
  t = Math.max(-1, Math.min(1, t));
  if (t < 0) {{ let v=Math.round(220*(1+t)); return `rgb(${{v}},${{v}},220)`; }}
  let v=Math.round(220*(1-t)); return `rgb(220,${{v}},${{v}})`;
}}

// ── Thin-plate spline ──────────────────────────────────────────────────────────
function tpsInterp(pts, vs, nx, ny) {{
  const n = pts.length;
  function phi(r) {{ return r < 1e-10 ? 0 : r*r*Math.log(r); }}
  // Build A matrix
  const sz = n + 3;
  const A = Array.from({{length:sz}}, () => new Float64Array(sz));
  for (let i=0;i<n;i++) for (let j=0;j<n;j++) {{
    const dx=pts[i][0]-pts[j][0], dy=pts[i][1]-pts[j][1];
    A[i][j] = phi(Math.sqrt(dx*dx+dy*dy));
  }}
  for (let i=0;i<n;i++) {{ A[i][n]=1; A[i][n+1]=pts[i][0]; A[i][n+2]=pts[i][1]; A[n][i]=1; A[n+1][i]=pts[i][0]; A[n+2][i]=pts[i][1]; }}
  const b = [...vs, 0, 0, 0];
  // Gaussian elimination
  for (let col=0;col<sz;col++) {{
    let maxR=col;
    for (let r=col+1;r<sz;r++) if (Math.abs(A[r][col])>Math.abs(A[maxR][col])) maxR=r;
    [A[col],A[maxR]]=[A[maxR],A[col]]; [b[col],b[maxR]]=[b[maxR],b[col]];
    if (Math.abs(A[col][col])<1e-12) continue;
    for (let r=0;r<sz;r++) if (r!==col) {{
      const f=A[r][col]/A[col][col];
      for (let c=col;c<sz;c++) A[r][c]-=f*A[col][c];
      b[r]-=f*b[col];
    }}
  }}
  const w = b.map((v,i) => v/A[i][i]);
  // Evaluate on grid
  const Z = new Float32Array(ny*nx);
  for (let j=0;j<ny;j++) for (let i=0;i<nx;i++) {{
    const gx=i/(nx-1), gy=j/(ny-1);
    let v = w[n] + w[n+1]*gx + w[n+2]*gy;
    for (let k=0;k<n;k++) {{
      const dx=gx-pts[k][0], dy=gy-pts[k][1], r=Math.sqrt(dx*dx+dy*dy);
      v += w[k]*phi(r);
    }}
    Z[j*nx+i] = v;
  }}
  return Z;
}}

function heatmapRects(Z, nx, ny, x0, y0, W, H, absmax, blueRed) {{
  const pw=W/nx, ph=H/ny; let s='';
  for (let j=0;j<ny;j++) for (let i=0;i<nx;i++) {{
    const v=Z[j*nx+i];
    const col = blueRed ? colBR(v/Math.max(absmax,1e-6)) : colGR(Math.abs(v)/Math.max(absmax,1e-6));
    s+=`<rect x="${{(x0+i*pw).toFixed(1)}}" y="${{(y0+j*ph).toFixed(1)}}" width="${{(pw+0.6).toFixed(1)}}" height="${{(ph+0.6).toFixed(1)}}" fill="${{col}}" opacity="0.9"/>`;
  }}
  return s;
}}

function colourBar(x0,y0,W,H,absmax,blueRed) {{
  const steps=60; let s='';
  for (let i=0;i<steps;i++) {{
    const t=i/steps;
    const col=blueRed?colBR(t*2-1):colGR(t);
    s+=`<rect x="${{(x0+i*W/steps).toFixed(1)}}" y="${{y0}}" width="${{(W/steps+0.5).toFixed(1)}}" height="${{H}}" fill="${{col}}"/>`;
  }}
  s+=`<rect x="${{x0}}" y="${{y0}}" width="${{W}}" height="${{H}}" fill="none" stroke="#555" stroke-width="0.8"/>`;
  if (blueRed) {{
    s+=`<text x="${{x0}}" y="${{y0+H+12}}" font-size="9" fill="#6af">${{(-absmax).toFixed(1)}} µε (compression)</text>`;
    s+=`<text x="${{x0+W/2}}" y="${{y0+H+12}}" text-anchor="middle" font-size="9" fill="#aaa">0 µε</text>`;
    s+=`<text x="${{x0+W}}" y="${{y0+H+12}}" text-anchor="end" font-size="9" fill="#f87">${{absmax.toFixed(1)}} µε (tension)</text>`;
  }} else {{
    s+=`<text x="${{x0}}" y="${{y0+H+12}}" font-size="9" fill="#aaa">0 µε</text>`;
    s+=`<text x="${{x0+W/2}}" y="${{y0+H+12}}" text-anchor="middle" font-size="9" fill="#aaa">|Δε| from baseline</text>`;
    s+=`<text x="${{x0+W}}" y="${{y0+H+12}}" text-anchor="end" font-size="9" fill="#aaa">${{absmax.toFixed(1)}} µε</text>`;
  }}
  return s;
}}

const DEFS=`<defs>
  <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
    <path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>
  <marker id="ar2" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto">
    <path d="M9 1L1 5L9 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>
</defs>`;

// ── Build deck SVG ─────────────────────────────────────────────────────────────
function buildDeck(delta) {{
  const W=820,H=310,DX=80,DY=55,DW=680,DH=175;
  const pts=[...DECK_ZEROS], vs=DECK_ZEROS.map(()=>0);
  DECK.forEach(s=>{{ const v=delta[s.ch]; if(v!==undefined){{pts.push([s.nx,s.ny]);vs.push(v);}} }});
  const allAbs=vs.reduce((m,v)=>Math.max(m,Math.abs(v)),1);
  const Z=tpsInterp(pts,vs,90,30);
  let s=`<svg viewBox="0 0 ${{W}} ${{H}}" xmlns="http://www.w3.org/2000/svg">${{DEFS}}`;
  s+=`<text x="${{DX+DW/2}}" y="20" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Aluminium deck plate — STR-01 to STR-06   (Δε from baseline)</text>`;
  s+=`<text x="${{DX+DW/2}}" y="36" text-anchor="middle" font-size="10" fill="#777">Thin-plate spline · edges = 0 µε · zeroed at first stable reading</text>`;
  s+=heatmapRects(Z,90,30,DX,DY,DW,DH,allAbs,false);
  s+=`<rect x="${{DX}}" y="${{DY}}" width="${{DW}}" height="${{DH}}" rx="5" fill="none" stroke="#ccc" stroke-width="1.2"/>`;
  [[0,"Poutre C · Nord"],[0.5,"Poutre B"],[1,"Poutre A · Sud"]].forEach(([ny,lbl])=>{{
    const sy=DY+ny*DH;
    s+=`<line x1="${{DX}}" y1="${{sy}}" x2="${{DX+DW}}" y2="${{sy}}" stroke="#fff" stroke-width="1.8" opacity="0.4"/>`;
    s+=`<text x="${{DX-6}}" y="${{sy+4}}" text-anchor="end" font-size="8" fill="#888">${{lbl}}</text>`;
  }});
  [[0,"Aval"],[X_D1,"D1"],[0.5,"D2"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lbl])=>{{
    const sx=DX+nx*DW;
    s+=`<line x1="${{sx}}" y1="${{DY}}" x2="${{sx}}" y2="${{DY+DH}}" stroke="#fff" stroke-width="0.7" opacity="0.2" stroke-dasharray="3 3"/>`;
    s+=`<text x="${{sx}}" y="${{DY+DH+12}}" text-anchor="middle" font-size="8" fill="#666">${{lbl}}</text>`;
  }});
  s+=`<text x="${{DX+5}}" y="${{DY-7}}" font-size="9" fill="#aaa">← Côté aval (Mobile · Forêt)</text>`;
  s+=`<text x="${{DX+DW-5}}" y="${{DY-7}}" text-anchor="end" font-size="9" fill="#aaa">(Fixé · Autoroute 175) Côté amont →</text>`;
  DECK.forEach(sen=>{{
    const v=delta[sen.ch], sx=DX+sen.nx*DW, sy=DY+sen.ny*DH;
    const txt=v!==undefined?`Δ${{v>=0?"+":""}}${{v.toFixed(1)}} µε`:"N/A", AR=18;
    if(sen.angle===0) s+=`<line x1="${{sx-AR}}" y1="${{sy}}" x2="${{sx+AR}}" y2="${{sy}}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    else s+=`<line x1="${{sx}}" y1="${{sy-AR}}" x2="${{sx}}" y2="${{sy+AR}}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    const bw=76,bh=28,bx=sen.nx<0.8?sx+22:sx-22-bw,by=sy-bh/2;
    s+=`<rect x="${{bx}}" y="${{by}}" width="${{bw}}" height="${{bh}}" rx="4" fill="#0d1117" stroke="#fff" stroke-width="0.6" opacity="0.92"/>`;
    s+=`<text x="${{bx+bw/2}}" y="${{by+10}}" text-anchor="middle" font-size="8" font-weight="bold" fill="#ccc">${{sen.label}}</text>`;
    s+=`<text x="${{bx+bw/2}}" y="${{by+23}}" text-anchor="middle" font-size="10" font-weight="bold" fill="white">${{txt}}</text>`;
  }});
  s+=colourBar(DX,DY+DH+22,DW,11,allAbs,false);
  s+='</svg>';
  return s;
}}

// ── Build beams SVG — elevation view with midspan sensor values ───────────────
// Shows 3 beams as elevation (side view along bridge length 8120mm)
// All 18 STR sensors are at midspan cross-section
// Top flange: average of 2 upper gauges, Bottom flange: average of 2 lower gauges
// Contour: TPS interpolation — zero at supports, measured values at midspan (x=0.5)
// Blue = compression, Red = tension

function safeMean(chs, d) {{
  const vs = chs.map(c=>d[c]||0);
  if (vs.length > 1) {{
    const med = [...vs].sort((a,b)=>a-b)[Math.floor(vs.length/2)];
    const filt = vs.filter(v=>Math.abs(v-med)<300);
    return filt.length ? filt.reduce((a,b)=>a+b,0)/filt.length : 0;
  }}
  return vs[0]||0;
}}

function buildBeams(delta) {{
  const W=820, DX=75, DW=680, BH=90, FH=18, GAP=80, DY=40;
  const H=DY+28+3*(BH+GAP)+30;
  let s=`<svg viewBox="0 0 ${{W}} ${{H}}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${{DX+DW/2}}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Steel girders — STR-07 to STR-18   (Δε from baseline)</text>`;
  s+=`<text x="${{DX+DW/2}}" y="32" text-anchor="middle" font-size="10" fill="#777">Elevation view · sensors at midspan cross-section · simply-supported · blue=compression · red=tension</text>`;

  let allAbs=1;
  const beamResults=[];

  BEAMS.forEach((beam,bi)=>{{
    const y0=DY+28+bi*(BH+GAP);
    const col=beam.color;
    const tv=safeMean(beam.top,delta);
    const bv=safeMean(beam.bot,delta);
    allAbs=Math.max(allAbs,Math.abs(tv),Math.abs(bv));
    beamResults.push({{...beam,tv,bv,y0}});

    // TPS interpolation: zero at supports, measured at midspan top+bot
    const pts=[], vs=[];
    [0,0.25,0.5,0.75,1].forEach(yy=>{{
      pts.push([0,yy]);vs.push(0);   // left support
      pts.push([1,yy]);vs.push(0);   // right support
    }});
    pts.push([0.5,0]); vs.push(tv);   // midspan top flange
    pts.push([0.5,1]); vs.push(bv);   // midspan bottom flange
    pts.push([0.5,0.5]); vs.push((tv+bv)/2);  // midspan neutral axis

    const Z=tpsInterp(pts,vs,80,20);
    const abm=Z.reduce((m,v)=>Math.max(m,Math.abs(v)),1);

    s+=heatmapRects(Z,80,20,DX,y0,DW,BH,abm,true);

    // I-beam outline
    s+=`<rect x="${{DX}}" y="${{y0}}" width="${{DW}}" height="${{FH}}" fill="none" stroke="${{col}}" stroke-width="2.5" opacity="0.9"/>`;
    s+=`<rect x="${{DX}}" y="${{y0+BH-FH}}" width="${{DW}}" height="${{FH}}" fill="none" stroke="${{col}}" stroke-width="2.5" opacity="0.9"/>`;
    s+=`<rect x="${{DX}}" y="${{y0}}" width="${{DW}}" height="${{BH}}" fill="none" stroke="${{col}}" stroke-width="1.2"/>`;

    // Midspan vertical dashed line
    const mx=DX+DW/2;
    s+=`<line x1="${{mx}}" y1="${{y0}}" x2="${{mx}}" y2="${{y0+BH}}" stroke="${{col}}" stroke-width="1" stroke-dasharray="4 3" opacity="0.6"/>`;

    // Flange labels (left side)
    s+=`<text x="${{DX-6}}" y="${{y0+FH/2+4}}" text-anchor="end" font-size="8" fill="${{col}}">top</text>`;
    s+=`<text x="${{DX-6}}" y="${{y0+BH-FH/2+4}}" text-anchor="end" font-size="8" fill="${{col}}">bot</text>`;

    // Beam name
    s+=`<text x="${{DX+DW/2}}" y="${{y0-10}}" text-anchor="middle" font-size="10" font-weight="bold" fill="${{col}}">${{beam.name}}</text>`;

    // Sensor diamonds ON the flanges at midspan (x=centre)
    const ty_=y0+FH/2, by_=y0+BH-FH/2, r=11;

    // Top flange diamond
    s+=`<polygon points="${{mx}},${{ty_-r}} ${{mx+r}},${{ty_}} ${{mx}},${{ty_+r}} ${{mx-r}},${{ty_}}" fill="#0d1117" stroke="${{col}}" stroke-width="2.5"/>`;
    s+=`<text x="${{mx}}" y="${{ty_-1}}" text-anchor="middle" font-size="7" font-weight="bold" fill="${{col}}">T</text>`;
    s+=`<text x="${{mx}}" y="${{ty_+10}}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">Δ${{tv>=0?"+":""}}${{tv.toFixed(1)}}</text>`;
    s+=`<text x="${{mx}}" y="${{y0-24}}" text-anchor="middle" font-size="8" fill="#aaa">${{beam.topLabel}}</text>`;

    // Bottom flange diamond
    s+=`<polygon points="${{mx}},${{by_-r}} ${{mx+r}},${{by_}} ${{mx}},${{by_+r}} ${{mx-r}},${{by_}}" fill="#0d1117" stroke="${{col}}" stroke-width="2.5"/>`;
    s+=`<text x="${{mx}}" y="${{by_-1}}" text-anchor="middle" font-size="7" font-weight="bold" fill="${{col}}">B</text>`;
    s+=`<text x="${{mx}}" y="${{by_+10}}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">Δ${{bv>=0?"+":""}}${{bv.toFixed(1)}}</text>`;
    s+=`<text x="${{mx}}" y="${{y0+BH+26}}" text-anchor="middle" font-size="8" fill="#aaa">${{beam.botLabel}}</text>`;

    // Support triangles
    [DX,DX+DW].forEach(sx=>{{
      s+=`<polygon points="${{sx}},${{y0+BH}} ${{sx-8}},${{y0+BH+14}} ${{sx+8}},${{y0+BH+14}}" fill="#888" opacity="0.8"/>`;
    }});

    // x-axis ticks
    [[0,"Aval"],[X_D1,"D1"],[X_MID,"midspan"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lbl])=>{{
      const sx=DX+nx*DW;
      s+=`<line x1="${{sx}}" y1="${{y0+BH}}" x2="${{sx}}" y2="${{y0+BH+6}}" stroke="#444" stroke-width="0.8"/>`;
      s+=`<text x="${{sx}}" y="${{y0+BH+16}}" text-anchor="middle" font-size="8" fill="#555">${{lbl}}</text>`;
    }});
  }});

  // Shared colour bar
  const barY=DY+28+3*(BH+GAP)-GAP+32;
  s+=colourBar(DX,barY,DW,11,allAbs,true);
  s+='</svg>';
  return s;
}}

// ── Build deflection SVG — curvature integration ───────────────────────────────
// κ(x) = (ε_top − ε_bot) / h  at midspan
// For simply-supported beam with central point load:
//   κ(x) is maximum at midspan, zero at supports
//   Use parabolic shape: κ(x) = κ_max * 4x(1-x)
//   Then double-integrate analytically
// v(x) = κ_max * L² * (x/6 - x³/6 + x²/2 - x/3) ... simplified to:
// v(x) ∝ κ_max * x*(1-x)  (parabolic, max at midspan)
// Scale to mm using L=8120mm and h=1200mm

const BEAM_H_MM = 1200;

function buildDeflection(delta) {{
  const W=820, H=260, DX=80, DY=50, DW=680, DH=150;
  const NX=200;
  const xs=Array.from({{length:NX}},(_,i)=>i/(NX-1));

  // Compute deflection for each beam
  const results=BEAMS.map(beam=>{{
    const tv=safeMean(beam.top,delta);
    const bv=safeMean(beam.bot,delta);
    // Curvature at midspan (microstrain/mm)
    const kappa_mid=(tv-bv)/BEAM_H_MM;
    // Simply-supported beam with central load: κ(x) = κ_max * 4x(1-x) (parabolic)
    // Double integrate: v(x) = κ_max * L² * (2x³/3 - x⁴/3 - x²/3 + ...) 
    // Simplified closed form for parabolic κ: v(x) = κ_mid/2 * L² * x*(1-x)
    const L_mm=8120;
    const v=xs.map(x=>kappa_mid/2 * L_mm*L_mm * x*(1-x) * 1e-6);
    const v_max=v.reduce((m,vi)=>Math.max(m,Math.abs(vi)),0);
    return {{...beam,tv,bv,kappa_mid,v,v_max}};
  }});

  const maxDef=Math.max(...results.map(r=>r.v_max), 0.001);

  let s=`<svg viewBox="0 0 ${{W}} ${{H}}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${{DX+DW/2}}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Estimated deflection — curvature integration</text>`;
  s+=`<text x="${{DX+DW/2}}" y="32" text-anchor="middle" font-size="10" fill="#777">κ(x) = (Δε_top − Δε_bot) / h  ·  h = 1200 mm  ·  parabolic shape  ·  v(0)=v(L)=0</text>`;

  // Zero line
  const zeroY=DY+DH/2;
  s+=`<line x1="${{DX}}" y1="${{zeroY}}" x2="${{DX+DW}}" y2="${{zeroY}}" stroke="#444" stroke-width="1" stroke-dasharray="4 3"/>`;

  // Grid
  [[0,"Aval"],[X_D1,"D1"],[X_MID,"midspan"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lbl])=>{{
    const sx=DX+nx*DW;
    s+=`<line x1="${{sx}}" y1="${{DY}}" x2="${{sx}}" y2="${{DY+DH}}" stroke="#333" stroke-width="0.8" stroke-dasharray="3 3"/>`;
    s+=`<text x="${{sx}}" y="${{DY+DH+14}}" text-anchor="middle" font-size="8" fill="#555">${{lbl}}</text>`;
  }});

  // Supports
  [DX,DX+DW].forEach(sx=>{{
    s+=`<polygon points="${{sx}},${{DY+DH}} ${{sx-8}},${{DY+DH+14}} ${{sx+8}},${{DY+DH+14}}" fill="#888" opacity="0.8"/>`;
  }});

  // Deflection curves
  results.forEach((r,i)=>{{
    const pts=xs.map((x,j)=>{{
      const px=DX+x*DW;
      const py=zeroY+(r.v[j]/maxDef)*(DH/2-8);  // downward positive → y increases
      return `${{px.toFixed(1)}},${{py.toFixed(1)}}`;
    }}).join(' ');
    s+=`<polyline points="${{pts}}" fill="none" stroke="${{r.color}}" stroke-width="2.5" stroke-linejoin="round" opacity="0.9"/>`;

    // Peak label at midspan
    const mx=DX+DW/2, myi=Math.floor(NX/2);
    const mpy=zeroY+(r.v[myi]/maxDef)*(DH/2-8);
    const vStr=r.v[myi].toFixed(3);
    s+=`<circle cx="${{mx}}" cy="${{mpy.toFixed(1)}}" r="4" fill="${{r.color}}"/>`;
    const lblY=i===0?mpy-12:mpy+18;
    s+=`<text x="${{mx}}" y="${{lblY.toFixed(1)}}" text-anchor="middle" font-size="9" font-weight="bold" fill="${{r.color}}">${{r.name.split("—")[0].trim()}}: ${{vStr}} mm  (κ=${{r.kappa_mid.toFixed(4)}} µε/mm)</text>`;
  }});

  // Y scale
  s+=`<text x="${{DX-6}}" y="${{DY+10}}" text-anchor="end" font-size="8" fill="#555">+${{maxDef.toFixed(3)}}mm</text>`;
  s+=`<text x="${{DX-6}}" y="${{DY+DH}}" text-anchor="end" font-size="8" fill="#555">-${{maxDef.toFixed(3)}}mm</text>`;
  s+=`<text x="${{DX-6}}" y="${{zeroY+4}}" text-anchor="end" font-size="8" fill="#555">0</text>`;

  // Legend
  results.forEach((r,i)=>{{
    const lx=DX+i*210, ly=H-16;
    s+=`<line x1="${{lx}}" y1="${{ly}}" x2="${{lx+28}}" y2="${{ly}}" stroke="${{r.color}}" stroke-width="2.5"/>`;
    s+=`<text x="${{lx+34}}" y="${{ly+4}}" font-size="9" fill="#aaa">${{r.name.split("—")[0].trim()}}</text>`;
  }});
  s+=`<text x="${{DX+DW}}" y="${{H-16}}" text-anchor="end" font-size="9" fill="#555">↓ downward deflection</text>`;
  s+='</svg>';
  return s;
}}

// ── Tab switching ─────────────────────────────────────────────────────────────
let activeTab = 0;
function showTab(n) {{
  document.querySelectorAll('.tab-panel').forEach((p,i) => p.style.display = i===n?'block':'none');
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', i===n));
  activeTab = n;
  if (n===3) renderCharts();
}}

// ── History storage ────────────────────────────────────────────────────────────
const HISTORY_MAX = 600;  // 5 min at 0.5s
const DECK_CHS  = ["STR_1_B8901","STR_2_B8902","STR_3_B8903","STR_4_B8904","STR_5_B8905","STR_6_B8906"];
const BEAM_CHS  = ["STR_7_B8907","STR_8_B8908","STR_9_B8909","STR_10_B8910",
                   "STR_11_B8911","STR_12_B8912","STR_13_B8913","STR_14_B8914",
                   "STR_15_B8915","STR_16_B8916","STR_17_B8917","STR_18_B8918"];
const DECK_LBLS = ["STR-01","STR-02","STR-03","STR-04","STR-05","STR-06"];
const BEAM_LBLS = ["STR-07","STR-08","STR-09","STR-10","STR-11","STR-12",
                   "STR-13","STR-14","STR-15","STR-16","STR-17","STR-18"];

let historyTs    = [];
let historyDeck  = DECK_CHS.map(()=>[]);
let historyBeams = BEAM_CHS.map(()=>[]);

function pushHistory(ts, delta) {{
  historyTs.push(ts.slice(11,19));
  DECK_CHS.forEach((ch,i)  => historyDeck[i].push(delta[ch]||0));
  BEAM_CHS.forEach((ch,i)  => historyBeams[i].push(delta[ch]||0));
  if (historyTs.length > HISTORY_MAX) {{
    historyTs.shift();
    historyDeck.forEach(a=>a.shift());
    historyBeams.forEach(a=>a.shift());
  }}
}}

// ── Chart.js charts ────────────────────────────────────────────────────────────
let chartDeck=null, chartBeams=null;
const COLORS_DECK  = ["#f87171","#fb923c","#fbbf24","#34d399","#60a5fa","#a78bfa"];
const COLORS_BEAMS = ["#60a5fa","#93c5fd","#bfdbfe","#dbeafe",
                      "#34d399","#6ee7b7","#4ade80","#86efac",
                      "#f87171","#fca5a5","#fcd34d","#fdba74"];

function makeChart(id, labels, datasets) {{
  const ctx = document.getElementById(id).getContext('2d');
  return new Chart(ctx, {{
    type: 'line',
    data: {{ labels, datasets }},
    options: {{
      animation: false,
      responsive: true,
      plugins: {{
        legend: {{ labels: {{ color:'#aaa', font:{{ size:10 }}, boxWidth:12 }} }},
        tooltip: {{ mode:'index', intersect:false }}
      }},
      scales: {{
        x: {{ ticks:{{ color:'#555', maxTicksLimit:10, font:{{size:9}} }}, grid:{{ color:'#222' }} }},
        y: {{ ticks:{{ color:'#aaa', font:{{size:9}} }}, grid:{{ color:'#2a2a2a' }},
              title:{{ display:true, text:'Δε (µε)', color:'#666', font:{{size:9}} }} }}
      }},
      elements: {{ point:{{ radius:0 }}, line:{{ borderWidth:1.5 }} }}
    }}
  }});
}}

function renderCharts() {{
  if (historyTs.length < 2) return;
  const labels = historyTs;

  // Deck chart
  const deckDS = DECK_CHS.map((ch,i)=>{{
    return {{ label:DECK_LBLS[i], data:[...historyDeck[i]],
             borderColor:COLORS_DECK[i], backgroundColor:'transparent', tension:0.2 }};
  }});
  if (!chartDeck) {{
    chartDeck = makeChart('chart-deck', labels, deckDS);
  }} else {{
    chartDeck.data.labels = labels;
    deckDS.forEach((ds,i)=>{{ chartDeck.data.datasets[i].data=ds.data; }});
    chartDeck.update('none');
  }}

  // Beam chart
  const beamDS = BEAM_CHS.map((ch,i)=>{{
    return {{ label:BEAM_LBLS[i], data:[...historyBeams[i]],
             borderColor:COLORS_BEAMS[i], backgroundColor:'transparent', tension:0.2 }};
  }});
  if (!chartBeams) {{
    chartBeams = makeChart('chart-beams', labels, beamDS);
  }} else {{
    chartBeams.data.labels = labels;
    beamDS.forEach((ds,i)=>{{ chartBeams.data.datasets[i].data=ds.data; }});
    chartBeams.update('none');
  }}
}}

// ── Poll loop ──────────────────────────────────────────────────────────────────// ── Tab switching ─────────────────────────────────────────────────────────────
let activeTab = 0;
function showTab(n) {{
  document.querySelectorAll('.tab-panel').forEach((p,i) => p.style.display = i===n?'block':'none');
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', i===n));
  activeTab = n;
  if (n===3) renderCharts();
}}

// ── History storage ────────────────────────────────────────────────────────────
const HISTORY_MAX = 600;  // 5 min at 0.5s
const DECK_CHS  = ["STR_1_B8901","STR_2_B8902","STR_3_B8903","STR_4_B8904","STR_5_B8905","STR_6_B8906"];
const BEAM_CHS  = ["STR_7_B8907","STR_8_B8908","STR_9_B8909","STR_10_B8910",
                   "STR_11_B8911","STR_12_B8912","STR_13_B8913","STR_14_B8914",
                   "STR_15_B8915","STR_16_B8916","STR_17_B8917","STR_18_B8918"];
const DECK_LBLS = ["STR-01","STR-02","STR-03","STR-04","STR-05","STR-06"];
const BEAM_LBLS = ["STR-07","STR-08","STR-09","STR-10","STR-11","STR-12",
                   "STR-13","STR-14","STR-15","STR-16","STR-17","STR-18"];

let historyTs    = [];
let historyDeck  = DECK_CHS.map(()=>[]);
let historyBeams = BEAM_CHS.map(()=>[]);

function pushHistory(ts, delta) {{
  historyTs.push(ts.slice(11,19));
  DECK_CHS.forEach((ch,i)  => historyDeck[i].push(delta[ch]||0));
  BEAM_CHS.forEach((ch,i)  => historyBeams[i].push(delta[ch]||0));
  if (historyTs.length > HISTORY_MAX) {{
    historyTs.shift();
    historyDeck.forEach(a=>a.shift());
    historyBeams.forEach(a=>a.shift());
  }}
}}

// ── Chart.js charts ────────────────────────────────────────────────────────────
let chartDeck=null, chartBeams=null;
const COLORS_DECK  = ["#f87171","#fb923c","#fbbf24","#34d399","#60a5fa","#a78bfa"];
const COLORS_BEAMS = ["#60a5fa","#93c5fd","#bfdbfe","#dbeafe",
                      "#34d399","#6ee7b7","#4ade80","#86efac",
                      "#f87171","#fca5a5","#fcd34d","#fdba74"];

function makeChart(id, labels, datasets) {{
  const ctx = document.getElementById(id).getContext('2d');
  return new Chart(ctx, {{
    type: 'line',
    data: {{ labels, datasets }},
    options: {{
      animation: false,
      responsive: true,
      plugins: {{
        legend: {{ labels: {{ color:'#aaa', font:{{ size:10 }}, boxWidth:12 }} }},
        tooltip: {{ mode:'index', intersect:false }}
      }},
      scales: {{
        x: {{ ticks:{{ color:'#555', maxTicksLimit:10, font:{{size:9}} }}, grid:{{ color:'#222' }} }},
        y: {{ ticks:{{ color:'#aaa', font:{{size:9}} }}, grid:{{ color:'#2a2a2a' }},
              title:{{ display:true, text:'Δε (µε)', color:'#666', font:{{size:9}} }} }}
      }},
      elements: {{ point:{{ radius:0 }}, line:{{ borderWidth:1.5 }} }}
    }}
  }});
}}

function renderCharts() {{
  if (historyTs.length < 2) return;
  const labels = historyTs;

  // Deck chart
  const deckDS = DECK_CHS.map((ch,i)=>{{
    return {{ label:DECK_LBLS[i], data:[...historyDeck[i]],
             borderColor:COLORS_DECK[i], backgroundColor:'transparent', tension:0.2 }};
  }});
  if (!chartDeck) {{
    chartDeck = makeChart('chart-deck', labels, deckDS);
  }} else {{
    chartDeck.data.labels = labels;
    deckDS.forEach((ds,i)=>{{ chartDeck.data.datasets[i].data=ds.data; }});
    chartDeck.update('none');
  }}

  // Beam chart
  const beamDS = BEAM_CHS.map((ch,i)=>{{
    return {{ label:BEAM_LBLS[i], data:[...historyBeams[i]],
             borderColor:COLORS_BEAMS[i], backgroundColor:'transparent', tension:0.2 }};
  }});
  if (!chartBeams) {{
    chartBeams = makeChart('chart-beams', labels, beamDS);
  }} else {{
    chartBeams.data.labels = labels;
    beamDS.forEach((ds,i)=>{{ chartBeams.data.datasets[i].data=ds.data; }});
    chartBeams.update('none');
  }}
}}

// ── Poll loop ──────────────────────────────────────────────────────────────────
let lastTs = null;
let nReads = 0;

// Show placeholder while connecting
document.getElementById('deck-panel').innerHTML =
  '<p style="color:#555;text-align:center;padding:60px 20px;font-size:13px">⏳ Fetching data from GitHub…<br><br>' +
  'Make sure <code style="color:#60a5fa">reader.py</code> is running on the acquisition PC with a valid GitHub token.</p>';

async function poll() {{
  try {{
    const r = await fetch(GITHUB_RAW + "?t=" + Date.now());
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();

    if (data.ts === lastTs) return;  // no change — do nothing
    lastTs = data.ts;
    nReads++;

    const raw = data.values;

    // Accumulate baseline buffer
    baselineBuf.push({{...raw}});
    if (baselineBuf.length > BASELINE_MIN) baselineBuf.shift();

    if (!baseline && baselineBuf.length >= BASELINE_MIN) {{
      baseline = {{}};
      const chs = Object.keys(raw);
      chs.forEach(ch => {{
        const vals = baselineBuf.map(r => r[ch] || 0).sort((a,b)=>a-b);
        baseline[ch] = vals[Math.floor(vals.length/2)];  // median
      }});
    }}

    const delta = {{}};
    Object.keys(raw).forEach(ch => {{
      delta[ch] = baseline ? raw[ch] - (baseline[ch]||0) : 0;
    }});

    const bl = baseline ? `✅ baseline set` : `⏳ buffering (${{baselineBuf.length}}/${{BASELINE_MIN}})`;
    document.getElementById('status').textContent =
      `${{nReads % 2 === 0 ? "🔄" : "✅"}} ${{data.file}} | reads: ${{nReads}} | ${{data.ts.slice(11,19)}} UTC | ${{bl}}`;

    // Update SVGs in-place — no flash
    // Update history
    pushHistory(data.ts, delta);

    // Render all panels every cycle so tab switching is instant
    document.getElementById('deck-panel').innerHTML = buildDeck(delta);
    document.getElementById('beam-panel').innerHTML = buildBeams(delta);
    document.getElementById('deflection-panel').innerHTML = buildDeflection(delta);
    if (activeTab===3) renderCharts();

  }} catch(e) {{
    document.getElementById('status').textContent = `⚠️ ${{e}} — retrying…`;
  }}
}}

poll();
setInterval(poll, 500);
</script>
</body>
</html>"""

st.title("🌉 Bridge — Live Strain Monitor")
components.html(HTML, height=1900, scrolling=True)
