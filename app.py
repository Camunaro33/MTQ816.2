import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="ALU Bridge — Live Strain Monitor", page_icon="🌉", layout="wide")

GITHUB_RAW = "https://raw.githubusercontent.com/Camunaro33/MTQ816.2/main/last_values.json"

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;font-family:sans-serif;color:#ccc;padding:8px}
#topbar{display:flex;align-items:center;gap:10px;margin-bottom:8px}
#status{font-size:11px;color:#666;font-family:monospace;flex:1}
#clock{font-size:15px;font-weight:bold;color:#60a5fa;font-family:monospace}
.btn{background:#1c2333;border:1px solid #333;color:#aaa;padding:5px 14px;border-radius:6px;cursor:pointer;font-size:12px}
.btn:hover{background:#253048;color:#eee}
svg{width:100%;display:block}
h3{font-size:12px;color:#aaa;margin:10px 0 5px}
canvas{width:100%!important}
</style></head><body>
<div id="topbar">
  <div id="status">⏳ Connecting…</div>
  <button class="btn" onclick="toggleAbs()" id="mode-btn">Show: Δε from baseline</button>
  <button class="btn" onclick="resetBL()">🔄 Reset baseline</button>
  <div id="clock"></div>
</div>
<div id="deck-panel"></div>
<div id="beam-panel"></div>
<div id="defl-panel"></div>
<h3>📈 Deck — STR-01 to STR-06</h3>
<canvas id="cd" height="130"></canvas>
<h3>📈 Beams — STR-07 to STR-18</h3>
<canvas id="cb" height="130"></canvas>
<script>
const GURL="GITHUB_RAW_PH";
const L=8120,XD1=1075/8120,XM=.5,XD3=(1075+2985+2985/2)/8120;
const DECK=[
  {ch:"STR_1_B8901",lb:"STR-01",nx:1-1075/L,ny:.25,a:90},
  {ch:"STR_2_B8902",lb:"STR-02",nx:1-1075/L,ny:.75,a:90},
  {ch:"STR_3_B8903",lb:"STR-03",nx:.5,ny:.25,a:90},
  {ch:"STR_4_B8904",lb:"STR-04",nx:.5,ny:.75,a:90},
  {ch:"STR_5_B8905",lb:"STR-05",nx:XD1+.08,ny:.25,a:0},
  {ch:"STR_6_B8906",lb:"STR-06",nx:XD1+.08,ny:.75,a:0},
];
const DZ=[[0,0],[0,.5],[0,1],[1,0],[1,.5],[1,1],[XD1,0],[XD1,1],[XM,0],[XM,1],[XD3,0],[XD3,1]];
const BEAMS=[
  {n:"Poutre C — Nord/Amont",c:"#60a5fa",top:["STR_7_B8907","STR_9_B8909"],bot:["STR_8_B8908","STR_10_B8910"],tl:"STR-07,09",bl:"STR-08,10"},
  {n:"Poutre B — Centre",c:"#34d399",top:["STR_11_B8911","STR_13_B8913"],bot:["STR_12_B8912","STR_14_B8914"],tl:"STR-11,13",bl:"STR-12,14"},
  {n:"Poutre A — Sud/Aval",c:"#f87171",top:["STR_15_B8915","STR_17_B8917"],bot:["STR_16_B8916","STR_18_B8918"],tl:"STR-15,17",bl:"STR-16,18"},
];
const DCH=DECK.map(s=>s.ch);
const BCH=["STR_7_B8907","STR_8_B8908","STR_9_B8909","STR_10_B8910","STR_11_B8911","STR_12_B8912","STR_13_B8913","STR_14_B8914","STR_15_B8915","STR_16_B8916","STR_17_B8917","STR_18_B8918"];
const DLB=["STR-01","STR-02","STR-03","STR-04","STR-05","STR-06"];
const BLB=["STR-07","STR-08","STR-09","STR-10","STR-11","STR-12","STR-13","STR-14","STR-15","STR-16","STR-17","STR-18"];
function cGR(t){t=Math.max(0,Math.min(1,t));return t<.5?`rgb(${Math.round(255*t*2)},210,30)`:`rgb(230,${Math.round(210*(1-(t-.5)*2))},30)`;}
function cBR(t){t=Math.max(-1,Math.min(1,t));if(t<0){const v=Math.round(220*(1+t));return `rgb(${v},${v},220)`;}const v=Math.round(220*(1-t));return `rgb(220,${v},${v})`;}
function tps(pts,vs,nx,ny){
  const n=pts.length,phi=r=>r<1e-10?0:r*r*Math.log(r),sz=n+3;
  const A=Array.from({length:sz},()=>new Float64Array(sz));
  for(let i=0;i<n;i++)for(let j=0;j<n;j++){const dx=pts[i][0]-pts[j][0],dy=pts[i][1]-pts[j][1];A[i][j]=phi(Math.sqrt(dx*dx+dy*dy));}
  for(let i=0;i<n;i++){A[i][n]=1;A[i][n+1]=pts[i][0];A[i][n+2]=pts[i][1];A[n][i]=1;A[n+1][i]=pts[i][0];A[n+2][i]=pts[i][1];}
  const b=[...vs,0,0,0];
  for(let c=0;c<sz;c++){let mx=c;for(let r=c+1;r<sz;r++)if(Math.abs(A[r][c])>Math.abs(A[mx][c]))mx=r;[A[c],A[mx]]=[A[mx],A[c]];[b[c],b[mx]]=[b[mx],b[c]];if(Math.abs(A[c][c])<1e-12)continue;for(let r=0;r<sz;r++)if(r!==c){const f=A[r][c]/A[c][c];for(let k=c;k<sz;k++)A[r][k]-=f*A[c][k];b[r]-=f*b[c];}}
  const w=b.map((v,i)=>v/A[i][i]);
  const Z=new Float32Array(ny*nx);
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){const gx=i/(nx-1),gy=j/(ny-1);let v=w[n]+w[n+1]*gx+w[n+2]*gy;for(let k=0;k<n;k++){const dx=gx-pts[k][0],dy=gy-pts[k][1],r=Math.sqrt(dx*dx+dy*dy);v+=w[k]*phi(r);}Z[j*nx+i]=v;}
  return Z;
}
function hm(Z,nx,ny,x0,y0,W,H,am,br){const pw=W/nx,ph=H/ny;let s='';for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){const v=Z[j*nx+i],c=br?cBR(v/Math.max(am,1e-6)):cGR(Math.abs(v)/Math.max(am,1e-6));s+=`<rect x="${(x0+i*pw).toFixed(1)}" y="${(y0+j*ph).toFixed(1)}" width="${(pw+.6).toFixed(1)}" height="${(ph+.6).toFixed(1)}" fill="${c}" opacity=".9"/>`;}return s;}
function cbar(x0,y0,W,H,am,br){let s='';for(let i=0;i<60;i++){const t=i/60,c=br?cBR(t*2-1):cGR(t);s+=`<rect x="${(x0+i*W/60).toFixed(1)}" y="${y0}" width="${(W/60+.5).toFixed(1)}" height="${H}" fill="${c}"/>`;}s+=`<rect x="${x0}" y="${y0}" width="${W}" height="${H}" fill="none" stroke="#555" stroke-width=".8"/>`;if(br){s+=`<text x="${x0}" y="${y0+H+12}" font-size="9" fill="#6af">${(-am).toFixed(1)} µε</text><text x="${x0+W/2}" y="${y0+H+12}" text-anchor="middle" font-size="9" fill="#aaa">0</text><text x="${x0+W}" y="${y0+H+12}" text-anchor="end" font-size="9" fill="#f87">${am.toFixed(1)} µε</text>`;}else{s+=`<text x="${x0}" y="${y0+H+12}" font-size="9" fill="#aaa">0 µε</text><text x="${x0+W}" y="${y0+H+12}" text-anchor="end" font-size="9" fill="#aaa">${am.toFixed(1)} µε</text>`;}return s;}
const DF=`<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M1 1L9 5L1 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker><marker id="ar2" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M9 1L1 5L9 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round"/></marker></defs>`;
function sm(chs,d){const vs=chs.map(c=>d[c]||0);if(vs.length>1){const m=[...vs].sort((a,b)=>a-b)[Math.floor(vs.length/2)];const f=vs.filter(v=>Math.abs(v-m)<300);return f.length?f.reduce((a,b)=>a+b,0)/f.length:0;}return vs[0]||0;}

function buildDeck(d,lbl){
  const W=820,H=310,DX=80,DY=55,DW=680,DH=175;
  const pts=[...DZ],vs=DZ.map(()=>0);
  DECK.forEach(s=>{const v=d[s.ch];if(v!==undefined){pts.push([s.nx,s.ny]);vs.push(v);}});
  const am=vs.reduce((m,v)=>Math.max(m,Math.abs(v)),1);
  const Z=tps(pts,vs,90,30);
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${DF}`;
  s+=`<text x="${DX+DW/2}" y="20" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Aluminium deck — STR-01 to STR-06 (${lbl})</text>`;
  s+=`<text x="${DX+DW/2}" y="36" text-anchor="middle" font-size="10" fill="#777">Thin-plate spline · edges=0 µε at supports</text>`;
  s+=hm(Z,90,30,DX,DY,DW,DH,am,false);
  s+=`<rect x="${DX}" y="${DY}" width="${DW}" height="${DH}" rx="5" fill="none" stroke="#ccc" stroke-width="1.2"/>`;
  [[0,"Poutre C · Nord"],[.5,"Poutre B"],[1,"Poutre A · Sud"]].forEach(([ny,lb])=>{const sy=DY+ny*DH;s+=`<line x1="${DX}" y1="${sy}" x2="${DX+DW}" y2="${sy}" stroke="#fff" stroke-width="1.8" opacity=".4"/><text x="${DX-6}" y="${sy+4}" text-anchor="end" font-size="8" fill="#888">${lb}</text>`;});
  [[0,"Aval"],[XD1,"D1"],[XM,"D2"],[XD3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{const sx=DX+nx*DW;s+=`<line x1="${sx}" y1="${DY}" x2="${sx}" y2="${DY+DH}" stroke="#fff" stroke-width=".7" opacity=".2" stroke-dasharray="3 3"/><text x="${sx}" y="${DY+DH+12}" text-anchor="middle" font-size="8" fill="#666">${lb}</text>`;});
  s+=`<text x="${DX+5}" y="${DY-7}" font-size="9" fill="#aaa">← Côté aval</text><text x="${DX+DW-5}" y="${DY-7}" text-anchor="end" font-size="9" fill="#aaa">Côté amont →</text>`;
  DECK.forEach(sen=>{
    const v=d[sen.ch],sx=DX+sen.nx*DW,sy=DY+sen.ny*DH,AR=18;
    const txt=v!==undefined?`${v>=0?"+":""}${v.toFixed(1)} µε`:"N/A";
    if(sen.a===0)s+=`<line x1="${sx-AR}" y1="${sy}" x2="${sx+AR}" y2="${sy}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    else s+=`<line x1="${sx}" y1="${sy-AR}" x2="${sx}" y2="${sy+AR}" stroke="white" stroke-width="2.5" stroke-linecap="round" marker-start="url(#ar2)" marker-end="url(#ar)"/>`;
    const bw=76,bh=28,bx=sen.nx<.8?sx+22:sx-22-bw,by=sy-bh/2;
    s+=`<rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="4" fill="#0d1117" stroke="#fff" stroke-width=".6" opacity=".92"/><text x="${bx+bw/2}" y="${by+10}" text-anchor="middle" font-size="8" font-weight="bold" fill="#ccc">${sen.lb}</text><text x="${bx+bw/2}" y="${by+23}" text-anchor="middle" font-size="10" font-weight="bold" fill="white">${txt}</text>`;
  });
  s+=cbar(DX,DY+DH+22,DW,11,am,false);
  return s+'</svg>';
}

function buildBeams(d){
  const W=820,DX=75,DW=680,BH=90,FH=18,GAP=80,DY=40,H=DY+28+3*(BH+GAP)+30;
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${DX+DW/2}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Steel girders — STR-07 to STR-18</text>`;
  s+=`<text x="${DX+DW/2}" y="32" text-anchor="middle" font-size="10" fill="#777">Midspan · blue=compression · red=tension</text>`;
  let allAbs=1;
  BEAMS.forEach((b,bi)=>{
    const y0=DY+28+bi*(BH+GAP),col=b.c,tv=sm(b.top,d),bv=sm(b.bot,d);
    allAbs=Math.max(allAbs,Math.abs(tv),Math.abs(bv));
    const pts=[],vs=[];
    [0,.25,.5,.75,1].forEach(yy=>{pts.push([0,yy]);vs.push(0);pts.push([1,yy]);vs.push(0);});
    pts.push([.5,0]);vs.push(tv);pts.push([.5,1]);vs.push(bv);pts.push([.5,.5]);vs.push((tv+bv)/2);
    const Z=tps(pts,vs,80,20),abm=Z.reduce((m,v)=>Math.max(m,Math.abs(v)),1);
    s+=hm(Z,80,20,DX,y0,DW,BH,abm,true);
    s+=`<rect x="${DX}" y="${y0}" width="${DW}" height="${FH}" fill="none" stroke="${col}" stroke-width="2.5" opacity=".9"/>`;
    s+=`<rect x="${DX}" y="${y0+BH-FH}" width="${DW}" height="${FH}" fill="none" stroke="${col}" stroke-width="2.5" opacity=".9"/>`;
    s+=`<rect x="${DX}" y="${y0}" width="${DW}" height="${BH}" fill="none" stroke="${col}" stroke-width="1.2"/>`;
    s+=`<line x1="${DX+DW/2}" y1="${y0}" x2="${DX+DW/2}" y2="${y0+BH}" stroke="${col}" stroke-width="1" stroke-dasharray="4 3" opacity=".6"/>`;
    s+=`<text x="${DX-6}" y="${y0+FH/2+4}" text-anchor="end" font-size="8" fill="${col}">top</text><text x="${DX-6}" y="${y0+BH-FH/2+4}" text-anchor="end" font-size="8" fill="${col}">bot</text>`;
    s+=`<text x="${DX+DW/2}" y="${y0-10}" text-anchor="middle" font-size="10" font-weight="bold" fill="${col}">${b.n}</text>`;
    const mx=DX+DW/2,ty=y0+FH/2,by_=y0+BH-FH/2,r=11;
    s+=`<polygon points="${mx},${ty-r} ${mx+r},${ty} ${mx},${ty+r} ${mx-r},${ty}" fill="#0d1117" stroke="${col}" stroke-width="2.5"/>`;
    s+=`<text x="${mx}" y="${ty-1}" text-anchor="middle" font-size="7" font-weight="bold" fill="${col}">T</text><text x="${mx}" y="${ty+10}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">${tv>=0?"+":""}${tv.toFixed(1)}</text>`;
    s+=`<text x="${mx}" y="${y0-24}" text-anchor="middle" font-size="8" fill="#aaa">${b.tl}</text>`;
    s+=`<polygon points="${mx},${by_-r} ${mx+r},${by_} ${mx},${by_+r} ${mx-r},${by_}" fill="#0d1117" stroke="${col}" stroke-width="2.5"/>`;
    s+=`<text x="${mx}" y="${by_-1}" text-anchor="middle" font-size="7" font-weight="bold" fill="${col}">B</text><text x="${mx}" y="${by_+10}" text-anchor="middle" font-size="9" font-weight="bold" fill="white">${bv>=0?"+":""}${bv.toFixed(1)}</text>`;
    s+=`<text x="${mx}" y="${y0+BH+26}" text-anchor="middle" font-size="8" fill="#aaa">${b.bl}</text>`;
    [DX,DX+DW].forEach(sx=>s+=`<polygon points="${sx},${y0+BH} ${sx-8},${y0+BH+14} ${sx+8},${y0+BH+14}" fill="#888" opacity=".8"/>`);
    [[0,"Aval"],[XD1,"D1"],[XM,"mid"],[XD3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{const sx=DX+nx*DW;s+=`<line x1="${sx}" y1="${y0+BH}" x2="${sx}" y2="${y0+BH+6}" stroke="#444" stroke-width=".8"/><text x="${sx}" y="${y0+BH+16}" text-anchor="middle" font-size="8" fill="#555">${lb}</text>`;});
  });
  s+=cbar(DX,DY+28+3*(BH+GAP)-GAP+32,DW,11,allAbs,true);
  return s+'</svg>';
}

function buildDefl(d){
  const W=820,H=260,DX=80,DY=50,DW=680,DH=150,NX=200,xs=Array.from({length:NX},(_,i)=>i/(NX-1));
  const res=BEAMS.map(b=>{const tv=sm(b.top,d),bv=sm(b.bot,d),km=(tv-bv)/1200;const v=xs.map(x=>km/2*8120*8120*x*(1-x)*1e-6);return {...b,v,vm:v.reduce((m,vi)=>Math.max(m,Math.abs(vi)),0)};});
  const maxD=Math.max(...res.map(r=>r.vm),.001);
  const zY=DY+DH/2;
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  s+=`<text x="${DX+DW/2}" y="18" text-anchor="middle" font-size="13" font-weight="bold" fill="#eee">Estimated deflection</text>`;
  s+=`<text x="${DX+DW/2}" y="32" text-anchor="middle" font-size="10" fill="#777">κ=(ε_top−ε_bot)/1200mm · v=κL²x(1−x)/2 · ±${maxD.toFixed(3)}mm</text>`;
  s+=`<line x1="${DX}" y1="${zY}" x2="${DX+DW}" y2="${zY}" stroke="#444" stroke-width="1" stroke-dasharray="4 3"/>`;
  [[0,"Aval"],[XD1,"D1"],[XM,"mid"],[XD3,"D3"],[1,"Amont"]].forEach(([nx,lb])=>{const sx=DX+nx*DW;s+=`<line x1="${sx}" y1="${DY}" x2="${sx}" y2="${DY+DH}" stroke="#333" stroke-width=".8" stroke-dasharray="3 3"/><text x="${sx}" y="${DY+DH+14}" text-anchor="middle" font-size="8" fill="#555">${lb}</text>`;});
  [DX,DX+DW].forEach(sx=>s+=`<polygon points="${sx},${DY+DH} ${sx-8},${DY+DH+14} ${sx+8},${DY+DH+14}" fill="#888" opacity=".8"/>`);
  res.forEach((r,i)=>{
    const pts=xs.map((x,j)=>`${(DX+x*DW).toFixed(1)},${(zY+(r.v[j]/maxD)*(DH/2-8)).toFixed(1)}`).join(' ');
    s+=`<polyline points="${pts}" fill="none" stroke="${r.c}" stroke-width="2.5" opacity=".9"/>`;
    const mpy=zY+(r.v[Math.floor(NX/2)]/maxD)*(DH/2-8);
    s+=`<circle cx="${DX+DW/2}" cy="${mpy.toFixed(1)}" r="4" fill="${r.c}"/>`;
    const ly=i===0?mpy-14:mpy+18;
    s+=`<text x="${DX+DW/2}" y="${ly.toFixed(1)}" text-anchor="middle" font-size="9" font-weight="bold" fill="${r.c}">${r.n.split("—")[0].trim()}: ${r.v[Math.floor(NX/2)].toFixed(3)} mm</text>`;
  });
  s+=`<text x="${DX-6}" y="${DY+10}" text-anchor="end" font-size="8" fill="#555">+${maxD.toFixed(3)}mm</text>`;
  s+=`<text x="${DX-6}" y="${DY+DH}" text-anchor="end" font-size="8" fill="#555">-${maxD.toFixed(3)}mm</text>`;
  s+=`<text x="${DX-6}" y="${zY+4}" text-anchor="end" font-size="8" fill="#555">0</text>`;
  return s+'</svg>';
}

const HMAX=600;let hTs=[],hD=DCH.map(()=>[]),hB=BCH.map(()=>[]);
let cD=null,cB=null;
const CD=["#f87171","#fb923c","#fbbf24","#34d399","#60a5fa","#a78bfa"];
const CB=["#60a5fa","#93c5fd","#bfdbfe","#dbeafe","#34d399","#6ee7b7","#4ade80","#86efac","#f87171","#fca5a5","#fcd34d","#fdba74"];
function pushH(d){const ts=new Date().toLocaleTimeString();hTs.push(ts);DCH.forEach((ch,i)=>hD[i].push(d[ch]||0));BCH.forEach((ch,i)=>hB[i].push(d[ch]||0));if(hTs.length>HMAX){hTs.shift();hD.forEach(a=>a.shift());hB.forEach(a=>a.shift());}}
function mkC(id,cols,lbs){const ctx=document.getElementById(id).getContext('2d');return new Chart(ctx,{type:'line',data:{labels:hTs,datasets:cols.map((c,i)=>({label:lbs[i],data:[],borderColor:c,backgroundColor:'transparent',tension:.2}))},options:{animation:false,responsive:true,plugins:{legend:{labels:{color:'#aaa',font:{size:9},boxWidth:10}}},scales:{x:{ticks:{color:'#555',maxTicksLimit:8,font:{size:8}},grid:{color:'#1a1a1a'}},y:{ticks:{color:'#aaa',font:{size:9}},grid:{color:'#222'},title:{display:true,text:'µε',color:'#555',font:{size:9}}}},elements:{point:{radius:0},line:{borderWidth:1.5}}}});}
function renderH(){if(hTs.length<2)return;if(!cD)cD=mkC('cd',CD,DLB);if(!cB)cB=mkC('cb',CB,BLB);cD.data.labels=hTs;hD.forEach((ds,i)=>cD.data.datasets[i].data=ds);cD.update('none');cB.data.labels=hTs;hB.forEach((ds,i)=>cB.data.datasets[i].data=ds);cB.update('none');}

let bl=null,blBuf=[],showAbs=false,lastRaw={},lastDelta={},lastTs=null,nR=0;
function toggleAbs(){showAbs=!showAbs;document.getElementById('mode-btn').textContent=showAbs?'Show: Absolute values':'Show: Δε from baseline';render(showAbs?lastRaw:lastDelta);}
function resetBL(){bl=null;blBuf=[];}
function render(d){
  const lbl=showAbs?'Absolute µε':'Δε from baseline';
  document.getElementById('deck-panel').innerHTML=buildDeck(d,lbl);
  document.getElementById('beam-panel').innerHTML=buildBeams(d);
  document.getElementById('defl-panel').innerHTML=buildDefl(d);
  pushH(d);renderH();
}
function tick(){document.getElementById('clock').textContent=new Date().toLocaleTimeString();}
tick();setInterval(tick,1000);

async function poll(){
  try{
    const r=await fetch(GURL+"?t="+Date.now());
    if(!r.ok)throw new Error(r.status);
    const data=await r.json();
    if(data.ts===lastTs)return;
    lastTs=data.ts;nR++;
    lastRaw=data.values;
    blBuf.push({...lastRaw});
    if(blBuf.length>10)blBuf.shift();
    if(!bl&&blBuf.length>=10){bl={};Object.keys(lastRaw).forEach(ch=>{const vs=blBuf.map(r=>r[ch]||0).sort((a,b)=>a-b);bl[ch]=vs[Math.floor(vs.length/2)];});}
    lastDelta={};Object.keys(lastRaw).forEach(ch=>lastDelta[ch]=bl?lastRaw[ch]-(bl[ch]||0):0);
    const blS=bl?'✅ baseline set':`⏳ buffering (${blBuf.length}/10)`;
    document.getElementById('status').textContent=`${data.file} | reads:${nR} | ${data.ts.slice(11,19)} UTC | ${blS}`;
    render(showAbs?lastRaw:lastDelta);
  }catch(e){document.getElementById('status').textContent=`⚠️ ${e}`;}
}
poll();setInterval(poll,1000);
</script></body></html>""".replace("GITHUB_RAW_PH", GITHUB_RAW)

st.title("🌉 ALU Bridge — Live Strain Monitor")
components.html(HTML, height=2600, scrolling=True)
