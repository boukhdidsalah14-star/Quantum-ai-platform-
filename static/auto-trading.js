(()=>{
"use strict";
const $=id=>document.getElementById(id);
const STORE="quantum_internal_auto_v1";
const START={binary:63578,forex:13790,crypto:78578};
const NAMES={binary:"Olymp-style Binary",forex:"MetaTrader 4-style Forex",crypto:"Binance-style Crypto"};
const state=load();
const feeds={binary:{symbol:"",price:null,market:""},forex:{symbol:"",price:null,market:""},crypto:{symbol:"BTCUSDT",price:null,market:""}};
const busy={binary:false,forex:false,crypto:false};
function load(){try{const v=JSON.parse(localStorage.getItem(STORE)||"{}");return {accounts:{...START,...v.accounts},positions:v.positions||{},history:v.history||[],running:v.running||{},dailyLoss:v.dailyLoss||{},day:v.day||new Date().toISOString().slice(0,10),amount:v.amount||{binary:100,forex:100,crypto:100},expiry:v.expiry||{binary:5,forex:15,crypto:15},lossLimit:10};}catch(_){return {accounts:{...START},positions:{},history:[],running:{},dailyLoss:{},day:new Date().toISOString().slice(0,10),amount:{binary:100,forex:100,crypto:100},expiry:{binary:5,forex:15,crypto:15},lossLimit:10};}}
function save(){localStorage.setItem(STORE,JSON.stringify(state));}
function money(n){return "$"+Number(n||0).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});}
function safe(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
async function get(url){const r=await fetch(url,{cache:"no-store"});const b=await r.json();if(!r.ok)throw new Error(b.detail||"Market data unavailable");return b;}
function mount(p){
 const section=$(p);if(!section)return;
 const panel=document.createElement("div");panel.className="panel qai-auto-panel";panel.id="auto-"+p;
 panel.innerHTML="<div class='qai-auto-head'><div><b>QUANTUM AI · AUTOMATIC TRADING</b><div class='sub'>Public market analysis · In-app account execution</div></div><span class='qai-engine-pill'>QUANTUM AI ENGINE</span></div><div class='qai-auto-grid'><div><label>TRADE AMOUNT (USD)</label><input type='number' min='1' step='1' id='auto-"+p+"-amount' value='"+state.amount[p]+"'></div><div><label>"+(p==="binary"?"CONTRACT DURATION":"POSITION REVIEW")+"</label><select id='auto-"+p+"-expiry'>"+(p==="binary"?[1,2,3,5,10,15,30,60]:[5,15,30,60]).map(n=>"<option value='"+n+"' "+(state.expiry[p]===n?"selected":"")+">"+n+" min</option>").join("")+"</select></div><div><label>DAILY LOSS LIMIT</label><input type='number' id='auto-"+p+"-risk' value='10' min='1' max='10' disabled><small>10% maximum</small></div></div><div class='qai-auto-actions'><button class='primary' id='auto-"+p+"-start'>START AUTO TRADING</button><button class='secondary' id='auto-"+p+"-stop' disabled>STOP</button></div><div class='qai-auto-status' id='auto-"+p+"-status'>Engine stopped · Waiting for your command</div><div class='qai-auto-stats'><div><small>ACCOUNT BALANCE</small><strong id='auto-"+p+"-balance'>"+money(state.accounts[p])+"</strong></div><div><small>OPEN POSITION</small><strong id='auto-"+p+"-position'>NONE</strong></div><div><small>OPEN P/L</small><strong id='auto-"+p+"-pnl'>$0.00</strong></div><div><small>DAILY LOSS</small><strong id='auto-"+p+"-loss'>$0.00 / "+money(START[p]*.1)+"</strong></div></div><div class='qai-auto-analysis' id='auto-"+p+"-analysis'>Analyser: waiting for market candles…</div><div class='qai-auto-log' id='auto-"+p+"-log'></div>";
 section.appendChild(panel);
 $("auto-"+p+"-amount").addEventListener("change",e=>{const n=Number(e.target.value);if(Number.isFinite(n)&&n>0){state.amount[p]=Math.min(n,START[p]);e.target.value=state.amount[p];save();}});
 $("auto-"+p+"-expiry").addEventListener("change",e=>{state.expiry[p]=Number(e.target.value);save();});
 $("auto-"+p+"-start").addEventListener("click",()=>start(p));
 $("auto-"+p+"-stop").addEventListener("click",()=>stop(p));
 render(p);
}
function status(p,msg){const el=$("auto-"+p+"-status");if(el)el.textContent=msg;}
function render(p){
 const a=$("auto-"+p+"-balance"),pos=$("auto-"+p+"-position"),pnl=$("auto-"+p+"-pnl"),loss=$("auto-"+p+"-loss"),start=$("auto-"+p+"-start"),stop=$("auto-"+p+"-stop");
 if(a)a.textContent=money(state.accounts[p]);
 const t=state.positions[p];
 if(pos)pos.textContent=t?t.side+" "+t.symbol:"NONE";
 if(pnl){const value=t?unrealized(t,feeds[p].price):0;pnl.textContent=money(value);pnl.style.color=value>=0?"#18d995":"#ff526d";}
 if(loss)loss.textContent=money(state.dailyLoss[p]||0)+" / "+money(START[p]*.1);
 if(start)start.disabled=!!state.running[p];
 if(stop)stop.disabled=!state.running[p];
}
function unrealized(t,price){if(!t||!Number.isFinite(Number(price)))return 0;if(t.platform==="binary")return 0;return t.stake*((Number(price)-t.entry)/t.entry)*(t.side==="BUY"?1:-1);}
function log(p,msg){const el=$("auto-"+p+"-log");if(!el)return;const line=document.createElement("div");line.textContent=new Date().toLocaleTimeString()+" · "+msg;el.prepend(line);while(el.children.length>8)el.lastChild.remove();}
async function getSymbol(p){
 if(p==="crypto"){const raw=$("cryptoPair")?.value||"BTC/USDT";return raw.replace("/","").toUpperCase();}
 if(p==="forex"){const raw=$("selectedPair")?.textContent||"EUR/USD";const markets=await get("/api/deriv/markets?category=forex");const key=raw.replace(/[^A-Z]/gi,"").toUpperCase();const found=(markets.markets||[]).find(x=>String(x.symbol).replace(/^frx/i,"").toUpperCase()===key)||markets.markets?.[0];if(!found)throw new Error("No public Forex market available");return found.symbol;}
 const raw=$("binaryAsset")?.value||"EUR/USD";
 if(raw.includes("USDT")){const s=raw.replace("/","").toUpperCase();return {kind:"crypto",symbol:s};}
 const markets=await get("/api/deriv/markets?category=forex");const key=raw.replace(/[^A-Z]/gi,"").toUpperCase();const found=(markets.markets||[]).find(x=>String(x.symbol).replace(/^frx/i,"").toUpperCase()===key)||markets.markets?.[0];if(!found)throw new Error("No public binary market available");return {kind:"forex",symbol:found.symbol};
}
async function analyze(p,symbol){
 if(p==="crypto"||(p==="binary"&&symbol.kind==="crypto")){
  const s=typeof symbol==="string"?symbol:symbol.symbol;
  return await get("/api/signals/crypto/"+encodeURIComponent(s)+"?source=binance&timeframe=1h");
 }
 const s=typeof symbol==="string"?symbol:symbol.symbol;
 return await get("/api/signals/deriv/"+encodeURIComponent(s)+"?category=forex&timeframe=15m");
}
async function quote(p,symbol){
 const s=typeof symbol==="string"?symbol:symbol.symbol;
 if(p==="crypto"||(p==="binary"&&symbol.kind==="crypto")){
  const d=await get("/api/markets");const x=(d.markets||[]).find(x=>x.symbol===s);if(!x)throw new Error("No live public crypto quote for "+s);return Number(x.price);
 }
 const d=await get("/api/deriv/markets?category=forex");const x=(d.markets||[]).find(x=>x.symbol===s);if(!x||!Number.isFinite(Number(x.price)))throw new Error("No live public Forex quote for "+s);return Number(x.price);
}
async function drawRealChart(p,symbol,position,price){
 const isCrypto=p==="crypto"||(p==="binary"&&symbol.kind==="crypto");
 const raw=typeof symbol==="string"?symbol:symbol.symbol;
 const url=isCrypto?"/api/candles/"+encodeURIComponent(raw)+"?interval=1h&limit=72":"/api/deriv/candles/"+encodeURIComponent(raw)+"?granularity=900&count=72";
 const data=await get(url);const rows=(data.candles||[]).map(c=>({o:Number(c.open??c.o),h:Number(c.high??c.h),l:Number(c.low??c.l),c:Number(c.close??c.c)})).filter(c=>[c.o,c.h,c.l,c.c].every(Number.isFinite));
 const canvas=$(p==="binary"?"binaryChart":p==="forex"?"forexChart":"cryptoChart");if(!canvas||!rows.length)return;
 const ctx=canvas.getContext("2d"),w=canvas.clientWidth,h=canvas.clientHeight,dpr=window.devicePixelRatio||1;
 canvas.width=Math.max(1,w*dpr);canvas.height=Math.max(1,h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 let lo=Math.min(...rows.map(x=>x.l)),hi=Math.max(...rows.map(x=>x.h));if(position){lo=Math.min(lo,position.entry);hi=Math.max(hi,position.entry);}const pad=18,range=hi-lo||1,yy=v=>pad+(hi-v)/range*(h-pad*2),step=(w-pad*2)/rows.length,bw=Math.max(2,step*.62);
 ctx.strokeStyle="#233b55";ctx.lineWidth=1;for(let i=0;i<5;i++){const y=pad+(h-pad*2)*i/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
 rows.forEach((c,i)=>{const x=pad+i*step+step/2,up=c.c>=c.o,color=up?"#18d995":"#ff526d";ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,yy(c.h));ctx.lineTo(x,yy(c.l));ctx.stroke();ctx.fillRect(x-bw/2,Math.min(yy(c.o),yy(c.c)),bw,Math.max(1,Math.abs(yy(c.o)-yy(c.c))));});
 if(position){const y=yy(position.entry);ctx.setLineDash([5,4]);ctx.strokeStyle="#ffc857";ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle="#ffc857";ctx.font="bold 10px Arial";ctx.fillText("ENTRY "+position.side+" "+position.entry.toPrecision(7),8,Math.max(12,y-5));}
 if(Number.isFinite(price)){ctx.strokeStyle="#53b7ff";ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(0,yy(price));ctx.lineTo(w,yy(price));ctx.stroke();ctx.setLineDash([]);}
 const heading=canvas.closest(".panel")?.querySelector(".chart-top b");if(heading)heading.textContent=raw;
}
function start(p){
 if(state.running[p])return;
 state.running[p]=true;save();status(p,"Starting analyser · loading current public candles…");render(p);log(p,"Automatic trading started");
 tick(p);
}
function stop(p){state.running[p]=false;save();status(p,"ENGINE OFF · Any open position remains active until it is settled.");render(p);log(p,"Engine stopped by user");}
async function tick(p){
 if(!state.running[p]||busy[p])return;busy[p]=true;
 try{
  if(state.day!==new Date().toISOString().slice(0,10)){state.day=new Date().toISOString().slice(0,10);state.dailyLoss={};}
  const symbol=await getSymbol(p);const price=await quote(p,symbol);feeds[p]={symbol,price,market:typeof symbol==="string"?symbol:symbol.symbol};
  const signal=await analyze(p,symbol);const direction=signal.direction||"WAIT";await drawRealChart(p,symbol,state.positions[p]||null,price);
  const analysis=$("auto-"+p+"-analysis");if(analysis)analysis.textContent="ANALYSER · "+direction+" · "+signal.trend+" · RSI "+signal.rsi_14+" · "+signal.signal_strength+" confidence · "+(signal.reasons||[]).slice(0,2).join(" / ");
  const existing=state.positions[p];
  if(existing){
   existing.mark=price;existing.unrealized=unrealized(existing,price);
   if(p==="binary"){
    if(Date.now()>=existing.expiresAt){const won=(price>existing.entry&&existing.side==="CALL")||(price<existing.entry&&existing.side==="PUT");const pnl=price===existing.entry?0:(won?existing.stake*.82:-existing.stake);settle(p,existing,price,pnl,won?"WIN":pnl===0?"DRAW":"LOSS");}
   }else{
    const move=existing.unrealized/Math.max(existing.stake,1);
    if(move>=.015||move<=-.01||Date.now()-existing.openedAt>=Number(state.expiry[p])*60000||(direction!=="WAIT"&&((direction==="CALL"&&existing.side==="SELL")||(direction==="PUT"&&existing.side==="BUY")))){
     settle(p,existing,price,existing.unrealized,existing.unrealized>=0?"WIN":"LOSS");
    }
   }
  }else if(direction!=="WAIT"&&Math.abs(Number(signal.score||0))>=3){
   const amount=Number(state.amount[p]);const daily=Number(state.dailyLoss[p]||0);const maxLoss=START[p]*.10;
   if(amount>state.accounts[p]){status(p,"TRADING PAUSED · Trade amount exceeds available account balance.");}
   else if(daily>=maxLoss||daily+amount>maxLoss){state.running[p]=false;status(p,"RISK STOP · 10% daily loss allowance reached.");log(p,"Risk limit paused the engine");}
   else{
    const side=p==="binary"?direction:(direction==="CALL"?"BUY":"SELL");
    const duration=Number(state.expiry[p]);
    state.positions[p]={id:"QAI-"+Date.now(),platform:p,symbol:typeof symbol==="string"?symbol:symbol.symbol,side,stake:amount,entry:price,mark:price,openedAt:Date.now(),expiresAt:Date.now()+duration*60000,expiry:duration};
    status(p,"TRADE OPEN · "+side+" "+state.positions[p].symbol+" at "+price+" · in-app order");
    log(p,"TRADE OPEN "+side+" "+state.positions[p].symbol+" · "+money(amount)+" at "+price);
   }
  }else status(p,"MARKET DATA CONNECTED · ENGINE ON · "+(direction==="WAIT"?"No qualified signal; waiting.":direction+" signal below entry threshold."));
  render(p);save();
 }catch(e){status(p,"MARKET DATA ERROR · "+e.message);}
 finally{busy[p]=false;if(state.running[p])setTimeout(()=>tick(p),12000);}
}
function settle(p,t,price,pnl,result){
 state.accounts[p]=Number(state.accounts[p])+Number(pnl);
 if(pnl<0)state.dailyLoss[p]=Number(state.dailyLoss[p]||0)+Math.abs(pnl);
 state.history.unshift({time:Date.now(),platform:p,symbol:t.symbol,side:t.side,stake:t.stake,entry:t.entry,exit:price,pnl,result});
 state.history=state.history.slice(0,100);delete state.positions[p];save();
 status(p,(result==="WIN"?"WIN":result==="LOSS"?"LOSS":"DRAW")+" · "+money(pnl)+" · exit "+price);
 log(p,result+" · "+money(pnl)+" · exit "+price);
 render(p);renderHistory();
}
function renderHistory(){
 const body=$("historyRows");if(!body)return;
 body.innerHTML=state.history.length?state.history.slice(0,20).map(t=>"<tr><td>"+new Date(t.time).toLocaleString()+"</td><td>"+safe(t.symbol)+"</td><td>"+safe(t.platform.toUpperCase()+" "+t.side)+"</td><td>"+money(t.stake)+"</td><td class='"+(t.pnl>=0?"positive":"negative")+"'>"+money(t.pnl)+"</td><td>"+(t.result==="WIN"?"WIN":t.result==="LOSS"?"LOSS":"DRAW")+"</td></tr>").join(""):"<tr><td colspan='6' style='text-align:center;padding:28px;color:var(--muted)'>No completed trades yet.</td></tr>";
}
function renderPortfolio(){
 for(const p of ["binary","forex","crypto"])render(p);
 const total=Object.values(state.accounts).reduce((a,b)=>a+Number(b),0);
 const header=document.querySelector(".total strong");if(header)header.textContent=money(total);
 renderHistory();
}
const style=document.createElement("style");style.textContent=".qai-auto-panel{margin-top:18px;border-color:#245a79}.qai-auto-head{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.qai-engine-pill{font-size:9px;letter-spacing:1px;border:1px solid #d7a83e;color:#f2ce75;padding:7px 9px;border-radius:20px}.qai-auto-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:15px}.qai-auto-grid label{display:block;color:#91a6c2;font-size:10px;margin-bottom:6px}.qai-auto-grid input,.qai-auto-grid select{width:100%;padding:11px;border-radius:8px;border:1px solid #2b4059;background:#081321;color:#fff}.qai-auto-grid small{display:block;color:#f0c66c;font-size:9px;margin-top:4px}.qai-auto-actions{display:flex;gap:9px;margin-top:13px}.qai-auto-actions button{flex:1}.qai-auto-status,.qai-auto-analysis{margin-top:12px;padding:11px;border-radius:8px;background:#0a1625;color:#a9c9e9;font-size:11px;line-height:1.5}.qai-auto-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}.qai-auto-stats>div{padding:10px;background:#0b1726;border:1px solid #23364d;border-radius:9px;min-width:0}.qai-auto-stats small{display:block;color:#8ea2bd;font-size:9px}.qai-auto-stats strong{display:block;font-size:13px;margin-top:7px;overflow-wrap:anywhere}.qai-auto-log{font-size:10px;color:#92a6c0;max-height:90px;overflow:auto;margin-top:9px}.qai-auto-log div{padding:4px 0;border-bottom:1px solid #22334a}@media(max-width:600px){.qai-auto-grid{grid-template-columns:1fr 1fr}.qai-auto-stats{grid-template-columns:1fr 1fr}.qai-auto-actions{flex-direction:column}}";document.head.appendChild(style);
["binary","forex","crypto"].forEach(mount);
renderPortfolio();
["binary","forex","crypto"].forEach(p=>{if(state.running[p]){status(p,"Resuming Quantum AI engine…");tick(p);}});
window.addEventListener("beforeunload",save);
})();