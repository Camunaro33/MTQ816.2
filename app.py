"""
app.py — Bridge STR Live Monitor
Single HTML page polling GitHub for last_values.json every 500ms.
4 tabs: Deck contour | Beam elevation | Deflection | History charts
"""
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="ALU Bridge — Live Strain Monitor", page_icon="🌉", layout="wide")

GITHUB_RAW = "https://raw.githubusercontent.com/Camunaro33/MTQ816.2/main/last_values.json"

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;font-family:sans-serif;color:#ccc;padding:8px}
#status{font-size:11px;color:#556;padding:4px 0 8px;font-family:monospace}
.tabs{display:flex;gap:6px;margin-bottom:10px}
.tab{background:#1c2333;border:1px solid #333;color:#aaa;padding:6px 16px;
     border-radius:6px;cursor:pointer;font-size:12px;transition:all .15s}
.tab:hover{background:#253048;color:#eee}
.tab.active{background:#2563eb;border-color:#2563eb;color:#fff;font-weight:bold}
.panel{display:none}
.panel.active{display:block}
svg{width:100%;display:block}
canvas{width:100%!important}
h3{font-size:12px;color:#aaa;margin:10px 0 6px;padding:0 8px}
</style>
</head>
<body>
<div style="display:flex;align-items:center;gap:16px;padding:4px 0 8px">
  <div id="status" style="font-size:11px;color:#556;font-family:monospace;flex:1">⏳ Connecting to GitHub…</div>
  <div id="clock" style="font-size:14px;font-weight:bold;color:#60a5fa;font-family:monospace;min-width:90px;text-align:right"></div>
</div>
<div id="deck-panel"><p style="color:#444;padding:40px;text-align:center">Waiting for data…</p></div>
<div id="beam-panel"></div>
<div id="deflection-panel"></div>
<h3 style="margin:10px 0 6px;padding:0 4px;font-size:12px;color:#aaa">📈 Deck sensors — STR-01 to STR-06 (Δε from baseline)</h3>
<canvas id="chart-deck" height="140"></canvas>
<h3 style="margin:10px 0 6px;padding:0 4px;font-size:12px;color:#aaa">📈 Beam sensors — STR-07 to STR-18 (Δε from baseline)</h3>
<canvas id="chart-beams" height="140"></canvas>

<script>
const GITHUB_RAW = "GITHUB_RAW_PLACEHOLDER";
const L=8120, X_D1=1075/8120, X_MID=0.5, X_D3=(1075+2985+2985/2)/8120;

// No tabs — all panels visible

// ── Sensor layout ─────────────────────────────────────────────────────────────
const DECK=[
  {ch:"STR_1_B8901",label:"STR-01",nx:1-1075/L,ny:0.25,angle:90},
  {ch:"STR_2_B8902",label:"STR-02",nx:1-1075/L,ny:0.75,angle:90},
  {ch:"STR_3_B8903",label:"STR-03",nx:0.50,     ny:0.25,angle:90},
  {ch:"STR_4_B8904",label:"STR-04",nx:0.50,     ny:0.75,angle:90},
  {ch:"STR_5_B8905",label:"STR-05",nx:X_D1+0.08,ny:0.25,angle:0},
  {ch:"STR_6_B8906",label:"STR-06",nx:X_D1+0.08,ny:0.75,angle:0},
];
const DECK_ZEROS=[[0,0],[0,.5],[0,1],[1,0],[1,.5],[1,1],
  [X_D1,0],[X_D1,1],[X_MID,0],[X_MID,1],[X_D3,0],[X_D3,1]];

const BEAMS=[
  {key:"C",name:"Poutre C — Nord/Amont (Voie C)",color:"#60a5fa",
   top:["STR_7_B8907","STR_9_B8909"],bot:["STR_8_B8908","STR_10_B8910"],
   topLabel:"STR-07, STR-09",botLabel:"STR-08, STR-10"},
  {key:"B",name:"Poutre B — Centre (Voie B)",color:"#34d399",
   top:["STR_11_B8911","STR_13_B8913"],bot:["STR_12_B8912","STR_14_B8914"],
   topLabel:"STR-11, STR-13",botLabel:"STR-12, STR-14"},
  {key:"A",name:"Poutre A — Sud/Aval (Voie A)",color:"#f87171",
   top:["STR_15_B8915","STR_17_B8917"],bot:["STR_16_B8916","STR_18_B8918"],
   topLabel:"STR-15, STR-17",botLabel:"STR-16, STR-18"},
];

const DECK_CHS =DECK.map(s=>s.ch);
const BEAM_CHS =["STR_7_B8907","STR_8_B8908","STR_9_B8909","STR_10_B8910",
                 "STR_11_B8911","STR_12_B8912","STR_13_B8913","STR_14_B8914",
                 "STR_15_B8915","STR_16_B8916","STR_17_B8917","STR_18_B8918"];
const DECK_LBLS=["STR-01","STR-02","STR-03","STR-04","STR-05","STR-06"];
const BEAM_LBLS=["STR-07","STR-08","STR-09","STR-10","STR-11","STR-12",
                 "STR-13","STR-14","STR-15","STR-16","STR-17","STR-18"];

// ── Colour helpers ────────────────────────────────────────────────────────────
function colGR(t){
  t=Math.max(0,Math.min(1,t));
  return t<0.5?`rgb(${Math.round(255*t*2)},210,30)`:`rgb(230,${Math.round(210*(1-(t-0.5)*2))},30)`;
}
function colBR(t){
  t=Math.max(-1,Math.min(1,t));
  if(t<0){const v=Math.round(220*(1+t));return `rgb(${v},${v},220)`;}
  const v=Math.round(220*(1-t));return `rgb(220,${v},${v})`;
}

// ── TPS interpolation ─────────────────────────────────────────────────────────
function tpsInterp(pts,vs,nx,ny){
  const n=pts.length;
  function phi(r){return r<1e-10?0:r*r*Math.log(r);}
  const sz=n+3;
  const A=Array.from({length:sz},()=>new Float64Array(sz));
  for(let i=0;i<n;i++)for(let j=0;j<n;j++){
    const dx=pts[i][0]-pts[j][0],dy=pts[i][1]-pts[j][1];
    A[i][j]=phi(Math.sqrt(dx*dx+dy*dy));
  }
  for(let i=0;i<n;i++){A[i][n]=1;A[i][n+1]=pts[i][0];A[i][n+2]=pts[i][1];
    A[n][i]=1;A[n+1][i]=pts[i][0];A[n+2][i]=pts[i][1];}
  const b=[...vs,0,0,0];
  for(let col=0;col<sz;col++){
    let mx=col;
    for(let r=col+1;r<sz;r++)if(Math.abs(A[r][col])>Math.abs(A[mx][col]))mx=r;
    [A[col],A[mx]]=[A[mx],A[col]];[b[col],b[mx]]=[b[mx],b[col]];
    if(Math.abs(A[col][col])<1e-12)continue;
    for(let r=0;r<sz;r++)if(r!==col){
      const f=A[r][col]/A[col][col];
      for(let c=col;c<sz;c++)A[r][c]-=f*A[col][c];
      b[r]-=f*b[col];
    }
  }
  const w=b.map((v,i)=>v/A[i][i]);
  const Z=new Float32Array(ny*nx);
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
    const gx=i/(nx-1),gy=j/(ny-1);
    let v=w[n]+w[n+1]*gx+w[n+2]*gy;
    for(let k=0;k<n;k++){
      const dx=gx-pts[k][0],dy=gy-pts[k][1],r=Math.sqrt(dx*dx+dy*dy);
      v+=w[k]*phi(r);
    }
    Z[j*nx+i]=v;
  }
  return Z;
}

function heatmap(Z,nx,ny,x0,y0,W,H,absmax,br){
  const pw=W/nx,ph=H/ny;let s='';
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
    const v=Z[j*nx+i];
    const c=br?colBR(v/Math.max(absmax,1e-6)):colGR(Math.abs(v)/Math.max(absmax,1e-6));
    s+=`<rect x="${(x0+i*pw).toFixed(1)}" y="${(y0+j*ph).toFixed(1)}" width="${(pw+0.6).toFixed(1)}" height="${(ph+0.6).toFixed(1)}" fill="${c}" opacity="0.9"/>`;
  }
  return s;
}

function cbar(x0,y0,W,H,absmax,br){
  const steps=60;let s='';
  for(let i=0;i<steps;i++){
    const t=i/steps,c=br?colBR(t*2-1):colGR(t);
    s+=`<rect x="${(x0+i*W/steps).toFixed(1)}" y="${y0}" width="${(W/steps+0.5).toFixed(1)}" height="${H}" fill="${c}"/>`;
  }
  s+=`<rect x="${x0}" y="${y0}" width="${W}" height="${H}" fill="none" stroke="#555" stroke-width="0.8"/>`;
  if(br){
    s+=`<text x="${x0}" y="${y0+H+12}" font-size="9" fill="#6af">${(-absmax).toFixed(1)} µε (compression)</text>`;
    s+=`<text x="${x0+W/2}" y="${y0+H+12}" text-anchor="middle" font-size="9" fill="#aaa">0 µε</text>`;
    s+=`<text x="${x0+W}" y="${y0+H+12}" text-anchor="end" font-size="9" fill="#f87">${absmax.toFixed(1)} µε (tension)</text>`;
  } else {
    s+=`<text x="${x0}" y="${y0+H+12}" font-size="9" fill="#aaa">0 µε</text>`;
    s+=`<text x="${x0+W/2}" y="${y0+H+12}" text-anchor="middle" font-size="9" fill="#aaa">|Δε| from baseline</text>`;
    s+=`<text x="${x0+W}" y="${y0+H+12}" text-anchor="end" font-size="9" fill="#aaa">${absmax.toFixed(1)} µε</text>`;
  }
  return s;
}

const DEFS=`<defs>
<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
  <path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>
<marker id="ar2" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto">
  <path d="M9 1L1 5L9 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker>
</defs>`;

// ── Deck SVG ──────────────────────────────────────────────────────────────────
function buildDeck(d){
  const W=820,H=310,DX=80,DY=55,DW=680,DH=175;
  const pts=[...DECK_ZEROS],vs=DECK_ZEROS.map(()=>0);
  DECK.forEach(s=>{const v=d[s.ch];if(v!==undefined){pts.push([s.nx,s.ny]);vs.push(v);}});
  const abm=vs.reduce((m,v)=>Math.max(m,Math.abs(v)),1);
  const Z=tpsInterp(pts,vs,90,30);
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${DEFS}`;
  s+=`<text x="${DX+DW/2}" y="20" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Aluminium deck plate — STR-01 to STR-06   (Δε from baseline)</text>`;
  s+=`<text x="${DX+DW/2}" y="36" text-anchor="middle" font-size="10" fill="#777">Thin-plate spline · edges = 0 µε · zeroed at first stable reading</text>`;
  s+=heatmap(Z,90,30,DX,DY,DW,DH,abm,false);
  s+=`<rect x="${DX}" y="${DY}" width="${DW}" height="${DH}" rx="5" fill="none" stroke="#ccc" stroke-width="1.2"/>`;
  [[0,"Poutre C · Nord"],[0.5,"Poutre B"],[1,"Poutre A · Sud"]].forEach(([ny,lb])=>{
    const sy=DY+ny*DH;
    s+=`<line x1="${DX}" y1="${sy}" x2="${DX+DW}" y2="${sy}" stroke="#fff" stroke-width="1.8" opacity="0.4"/>`;
    s+=`<text x="${DX-6}" y="${sy+4}" text-anchor="end" font-size="8" fill="#888">${lb}</text>`;
  });
  [[0,"Aval"],[X_D1,"D1"],[0.5,"D2"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{
    const sx=DX+nx*DW;
    s+=`<line x1="${sx}" y1="${DY}" x2="${sx}" y2="${DY+DH}" stroke="#fff" stroke-width="0.7" opacity="0.2" stroke-dasharray="3 3"/>`;
    s+=`<text x="${sx}" y="${DY+DH+12}" text-anchor="middle" font-size="8" fill="#666">${lb}</text>`;
  });
  s+=`<text x="${DX+5}" y="${DY-7}" font-size="9" fill="#aaa">← Côté aval (Mobile · Forêt)</text>`;
  s+=`<text x="${DX+DW-5}" y="${DY-7}" text-anchor="end" font-size="9" fill="#aaa">(Fixé · Autoroute 175) Côté amont →</text>`;
  DECK.forEach(sen=>{
    const v=d[sen.ch],sx=DX+sen.nx*DW,sy=DY+sen.ny*DH;
    const txt=v!==undefined?`Δ${v>=0?"+":""}${v.toFixed(1)} µε`:"N/A",AR=18;
    if(sen.angle===0)
      s+=`<line x1="${sx-AR}" y1="${sy}" x2="${sx+AR}" y2="${sy}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    else
      s+=`<line x1="${sx}" y1="${sy-AR}" x2="${sx}" y2="${sy+AR}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    const bw=76,bh=28,bx=sen.nx<0.8?sx+22:sx-22-bw,by=sy-bh/2;
    s+=`<rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="4" fill="#0d1117" stroke="#fff" stroke-width="0.6" opacity="0.92"/>`;
    s+=`<text x="${bx+bw/2}" y="${by+10}" text-anchor="middle" font-size="8" font-weight="bold" fill="#ccc">${sen.label}</text>`;
    s+=`<text x="${bx+bw/2}" y="${by+23}" text-anchor="middle" font-size="10" font-weight="bold" fill="white">${txt}</text>`;
  });
  s+=cbar(DX,DY+DH+22,DW,11,abm,false);
  return s+'</svg>';
}

// ── Beams SVG ─────────────────────────────────────────────────────────────────
function safeMean(chs,d){
  const vs=chs.map(c=>d[c]||0);
  if(vs.length>1){
    const med=[...vs].sort((a,b)=>a-b)[Math.floor(vs.length/2)];
    const f=vs.filter(v=>Math.abs(v-med)<300);
    return f.length?f.reduce((a,b)=>a+b,0)/f.length:0;
  }
  return vs[0]||0;
}

function buildBeams(d){
  const W=820,DX=75,DW=680,BH=90,FH=18,GAP=80,DY=40;
  const H=DY+28+3*(BH+GAP)+30;
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${DX+DW/2}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Steel girders — STR-07 to STR-18   (Δε from baseline)</text>`;
  s+=`<text x="${DX+DW/2}" y="32" text-anchor="middle" font-size="10" fill="#777">Elevation view · all sensors at midspan cross-section · blue=compression · red=tension</text>`;
  let allAbs=1;
  BEAMS.forEach((beam,bi)=>{
    const y0=DY+28+bi*(BH+GAP),col=beam.color;
    const tv=safeMean(beam.top,d),bv=safeMean(beam.bot,d);
    allAbs=Math.max(allAbs,Math.abs(tv),Math.abs(bv));
    const pts=[],vs=[];
    [0,0.25,0.5,0.75,1].forEach(yy=>{pts.push([0,yy]);vs.push(0);pts.push([1,yy]);vs.push(0);});
    pts.push([0.5,0]);vs.push(tv);
    pts.push([0.5,1]);vs.push(bv);
    pts.push([0.5,0.5]);vs.push((tv+bv)/2);
    const Z=tpsInterp(pts,vs,80,20);
    const abm=Z.reduce((m,v)=>Math.max(m,Math.abs(v)),1);
    s+=heatmap(Z,80,20,DX,y0,DW,BH,abm,true);
    // I-beam
    s+=`<rect x="${DX}" y="${y0}" width="${DW}" height="${FH}" fill="none" stroke="${col}" stroke-width="2.5" opacity="0.9"/>`;
    s+=`<rect x="${DX}" y="${y0+BH-FH}" width="${DW}" height="${FH}" fill="none" stroke="${col}" stroke-width="2.5" opacity="0.9"/>`;
    s+=`<rect x="${DX}" y="${y0}" width="${DW}" height="${BH}" fill="none" stroke="${col}" stroke-width="1.2"/>`;
    // Midspan line
    s+=`<line x1="${DX+DW/2}" y1="${y0}" x2="${DX+DW/2}" y2="${y0+BH}" stroke="${col}" stroke-width="1" stroke-dasharray="4 3" opacity="0.6"/>`;
    // Flange labels
    s+=`<text x="${DX-6}" y="${y0+FH/2+4}" text-anchor="end" font-size="8" fill="${col}">top</text>`;
    s+=`<text x="${DX-6}" y="${y0+BH-FH/2+4}" text-anchor="end" font-size="8" fill="${col}">bot</text>`;
    s+=`<text x="${DX+DW/2}" y="${y0-10}" text-anchor="middle" font-size="10" font-weight="bold" fill="${col}">${beam.name}</text>`;
    // Diamonds on flanges at midspan
    const mx=DX+DW/2,ty=y0+FH/2,by_=y0+BH-FH/2,r=11;
    s+=`<polygon points="${mx},${ty-r} ${mx+r},${ty} ${mx},${ty+r} ${mx-r},${ty}" fill="#0d1117" stroke="${col}" stroke-width="2.5"/>`;
    s+=`<text x="${mx}" y="${ty-1}" text-anchor="middle" font-size="7" font-weight="bold" fill="${col}">T</text>`;
    s+=`<text x="${mx}" y="${ty+10}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">Δ${tv>=0?"+":""}${tv.toFixed(1)}</text>`;
    s+=`<text x="${mx}" y="${y0-24}" text-anchor="middle" font-size="8" fill="#aaa">${beam.topLabel}</text>`;
    s+=`<polygon points="${mx},${by_-r} ${mx+r},${by_} ${mx},${by_+r} ${mx-r},${by_}" fill="#0d1117" stroke="${col}" stroke-width="2.5"/>`;
    s+=`<text x="${mx}" y="${by_-1}" text-anchor="middle" font-size="7" font-weight="bold" fill="${col}">B</text>`;
    s+=`<text x="${mx}" y="${by_+10}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">Δ${bv>=0?"+":""}${bv.toFixed(1)}</text>`;
    s+=`<text x="${mx}" y="${y0+BH+26}" text-anchor="middle" font-size="8" fill="#aaa">${beam.botLabel}</text>`;
    // Supports
    [DX,DX+DW].forEach(sx=>{
      s+=`<polygon points="${sx},${y0+BH} ${sx-8},${y0+BH+14} ${sx+8},${y0+BH+14}" fill="#888" opacity="0.8"/>`;
    });
    [[0,"Aval"],[X_D1,"D1"],[X_MID,"midspan"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{
      const sx=DX+nx*DW;
      s+=`<line x1="${sx}" y1="${y0+BH}" x2="${sx}" y2="${y0+BH+6}" stroke="#444" stroke-width="0.8"/>`;
      s+=`<text x="${sx}" y="${y0+BH+16}" text-anchor="middle" font-size="8" fill="#555">${lb}</text>`;
    });
  });
  s+=cbar(DX,DY+28+3*(BH+GAP)-GAP+32,DW,11,allAbs,true);
  return s+'</svg>';
}

// ── Deflection SVG ────────────────────────────────────────────────────────────
const BEAM_H=1200;
function buildDeflection(d){
  const W=820,H=260,DX=80,DY=50,DW=680,DH=150,NX=200;
  const xs=Array.from({length:NX},(_,i)=>i/(NX-1));
  const results=BEAMS.map(b=>{
    const tv=safeMean(b.top,d),bv=safeMean(b.bot,d);
    const km=(tv-bv)/BEAM_H;
    const v=xs.map(x=>km/2*8120*8120*x*(1-x)*1e-6);
    return {...b,tv,bv,km,v,vmax:v.reduce((m,vi)=>Math.max(m,Math.abs(vi)),0)};
  });
  const maxD=Math.max(...results.map(r=>r.vmax),0.001);
  const zY=DY+DH/2;
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${DX+DW/2}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Estimated deflection — curvature integration</text>`;
  s+=`<text x="${DX+DW/2}" y="32" text-anchor="middle" font-size="10" fill="#777">κ = (Δε_top − Δε_bot) / h · h = 1200 mm · v(x) = κL²/2 · x(1−x) · v(0)=v(L)=0</text>`;
  s+=`<line x1="${DX}" y1="${zY}" x2="${DX+DW}" y2="${zY}" stroke="#444" stroke-width="1" stroke-dasharray="4 3"/>`;
  [[0,"Aval"],[X_D1,"D1"],[X_MID,"midspan"],[X_D3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{
    const sx=DX+nx*DW;
    s+=`<line x1="${sx}" y1="${DY}" x2="${sx}" y2="${DY+DH}" stroke="#333" stroke-width="0.8" stroke-dasharray="3 3"/>`;
    s+=`<text x="${sx}" y="${DY+DH+14}" text-anchor="middle" font-size="8" fill="#555">${lb}</text>`;
  });
  [DX,DX+DW].forEach(sx=>{
    s+=`<polygon points="${sx},${DY+DH} ${sx-8},${DY+DH+14} ${sx+8},${DY+DH+14}" fill="#888" opacity="0.8"/>`;
  });
  results.forEach((r,i)=>{
    const pts=xs.map((x,j)=>{
      const px=DX+x*DW,py=zY+(r.v[j]/maxD)*(DH/2-8);
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    }).join(' ');
    s+=`<polyline points="${pts}" fill="none" stroke="${r.color}" stroke-width="2.5" stroke-linejoin="round" opacity="0.9"/>`;
    const mx=DX+DW/2,mpy=zY+(r.v[Math.floor(NX/2)]/maxD)*(DH/2-8);
    const vStr=r.v[Math.floor(NX/2)].toFixed(3);
    s+=`<circle cx="${mx}" cy="${mpy.toFixed(1)}" r="4" fill="${r.color}"/>`;
    const ly=i===0?mpy-14:i===1?mpy+18:mpy-14;
    s+=`<text x="${mx}" y="${ly.toFixed(1)}" text-anchor="middle" font-size="9" font-weight="bold" fill="${r.color}">${r.name.split("—")[0].trim()}: ${vStr} mm</text>`;
  });
  s+=`<text x="${DX-6}" y="${DY+10}" text-anchor="end" font-size="8" fill="#555">+${maxD.toFixed(3)}mm</text>`;
  s+=`<text x="${DX-6}" y="${DY+DH}" text-anchor="end" font-size="8" fill="#555">-${maxD.toFixed(3)}mm</text>`;
  s+=`<text x="${DX-6}" y="${zY+4}" text-anchor="end" font-size="8" fill="#555">0</text>`;
  results.forEach((r,i)=>{
    const lx=DX+i*210,ly=H-16;
    s+=`<line x1="${lx}" y1="${ly}" x2="${lx+28}" y2="${ly}" stroke="${r.color}" stroke-width="2.5"/>`;
    s+=`<text x="${lx+34}" y="${ly+4}" font-size="9" fill="#aaa">${r.name.split("—")[0].trim()}</text>`;
  });
  s+=`<text x="${DX+DW}" y="${H-16}" text-anchor="end" font-size="9" fill="#555">↓ downward</text>`;
  return s+'</svg>';
}

// ── History charts ────────────────────────────────────────────────────────────
const HIST_MAX=600;
let histTs=[],histDeck=DECK_CHS.map(()=>[]),histBeams=BEAM_CHS.map(()=>[]);
let chartDeck=null,chartBeams=null;
const CDECK=["#f87171","#fb923c","#fbbf24","#34d399","#60a5fa","#a78bfa"];
const CBEAMS=["#60a5fa","#93c5fd","#bfdbfe","#dbeafe","#34d399","#6ee7b7",
              "#4ade80","#86efac","#f87171","#fca5a5","#fcd34d","#fdba74"];

function pushHistory(ts,d){
  histTs.push(ts.slice(11,19));
  DECK_CHS.forEach((ch,i)=>histDeck[i].push(d[ch]||0));
  BEAM_CHS.forEach((ch,i)=>histBeams[i].push(d[ch]||0));
  if(histTs.length>HIST_MAX){histTs.shift();histDeck.forEach(a=>a.shift());histBeams.forEach(a=>a.shift());}
}

function mkChart(id,labels,datasets){
  const ctx=document.getElementById(id).getContext('2d');
  return new Chart(ctx,{
    type:'line',data:{labels,datasets},
    options:{animation:false,responsive:true,
      plugins:{legend:{labels:{color:'#aaa',font:{size:10},boxWidth:12}}},
      scales:{
        x:{ticks:{color:'#555',maxTicksLimit:10,font:{size:9}},grid:{color:'#222'}},
        y:{ticks:{color:'#aaa',font:{size:9}},grid:{color:'#2a2a2a'},
           title:{display:true,text:'Δε (µε)',color:'#666',font:{size:9}}}
      },
      elements:{point:{radius:0},line:{borderWidth:1.5}}
    }
  });
}

function renderCharts(){
  if(histTs.length<2)return;
  const labels=histTs;
  const dDS=DECK_CHS.map((ch,i)=>({label:DECK_LBLS[i],data:[...histDeck[i]],borderColor:CDECK[i],backgroundColor:'transparent',tension:0.2}));
  if(!chartDeck)chartDeck=mkChart('chart-deck',labels,dDS);
  else{chartDeck.data.labels=labels;dDS.forEach((ds,i)=>chartDeck.data.datasets[i].data=ds.data);chartDeck.update('none');}
  const bDS=BEAM_CHS.map((ch,i)=>({label:BEAM_LBLS[i],data:[...histBeams[i]],borderColor:CBEAMS[i],backgroundColor:'transparent',tension:0.2}));
  if(!chartBeams)chartBeams=mkChart('chart-beams',labels,bDS);
  else{chartBeams.data.labels=labels;bDS.forEach((ds,i)=>chartBeams.data.datasets[i].data=ds.data);chartBeams.update('none');}
}

// ── Baseline ──────────────────────────────────────────────────────────────────
let baseline=null,baselineBuf=[];
const BL_MIN=10;

// ── Poll ──────────────────────────────────────────────────────────────────────
let lastTs=null,nReads=0,lastDelta=null;

async function poll(){
  try{
    const r=await fetch(GITHUB_RAW+"?t="+Date.now());
    if(!r.ok)throw new Error(r.status);
    const data=await r.json();
    if(data.ts===lastTs)return;
    lastTs=data.ts; nReads++;
    const raw=data.values;
    baselineBuf.push({...raw});
    if(baselineBuf.length>BL_MIN)baselineBuf.shift();
    if(!baseline&&baselineBuf.length>=BL_MIN){
      baseline={};
      Object.keys(raw).forEach(ch=>{
        const vs=baselineBuf.map(r=>r[ch]||0).sort((a,b)=>a-b);
        baseline[ch]=vs[Math.floor(vs.length/2)];
      });
    }
    const d={};
    Object.keys(raw).forEach(ch=>d[ch]=baseline?raw[ch]-(baseline[ch]||0):0);
    lastDelta=d;
    const bl=baseline?'✅ baseline set':`⏳ buffering (${baselineBuf.length}/${BL_MIN})`;
    document.getElementById('status').textContent=
      `${nReads%2===0?'🔄':'✅'} ${data.file} | reads: ${nReads} | data: ${data.ts.slice(11,19)} UTC | ${bl}`;
    pushHistory(data.ts,d);
    document.getElementById('deck-panel').innerHTML=buildDeck(d);
    document.getElementById('beam-panel').innerHTML=buildBeams(d);
    document.getElementById('deflection-panel').innerHTML=buildDeflection(d);
    renderCharts();
  }catch(e){
    document.getElementById('status').textContent=`⚠️ ${e} — retrying…`;
  }
}
poll();
setInterval(poll,500);

// Clock ticks every second
function updateClock(){
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
}
updateClock();
setInterval(updateClock, 1000);
</script>
</body>
</html>""".replace("GITHUB_RAW_PLACEHOLDER", GITHUB_RAW)

st.title("🌉 ALU Bridge — Live Strain Monitor")
components.html(HTML, height=2800, scrolling=True)
