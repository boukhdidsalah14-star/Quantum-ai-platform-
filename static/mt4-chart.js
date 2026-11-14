(()=>{
"use strict";
const $=id=>document.getElementById(id);
const canvas=$("mt4-trade-chart");
if(!canvas)return;
let symbol="XAUUSD",granularity=900,marketSymbol=null,lastCandles=[],mt4Positions=[],busy=false;
const state=$("mt4-chart-state"),priceEl=$("mt4-chart-price"),note=$("mt4-chart-note");
const label=s=>String(s||"").replace(/^frx/i,"");
async function get(url){const r=await fetch(url,{cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Market data unavailable");return d;}
function setState(t){if(state)state.textContent=t;}
function draw(rows){
 const w=canvas.clientWidth,h=canvas.clientHeight,dpr=window.devicePixelRatio||1;
 if(!w||!h)return;
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 const x=canvas.getContext("2d");x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);
 if(!rows.length){x.fillStyle="#8ca8c6";x.font="13px Inter,Arial";x.fillText("Waiting for verified market candles…",18,34);return;}
 const visiblePositions=mt4Positions.filter(p=>p.symbol===symbol);
 let levels=[];
 visiblePositions.forEach(p=>{levels.push(Number(p.open_price));if(Number(p.stop_loss)>0)levels.push(Number(p.stop_loss));if(Number(p.take_profit)>0)levels.push(Number(p.take_profit));});
 let lo=Math.min(...rows.map(c=>c.low),...levels),hi=Math.max(...rows.map(c=>c.high),...levels);
 const pad={l:12,r:80,t:18,b:20},range=(hi-lo)||1;
 const y=v=>pad.t+(hi-v)/range*(h-pad.t-pad.b),step=(w-pad.l-pad.r)/rows.length,bw=Math.max(2,step*.62);
 x.strokeStyle="#18334d";x.lineWidth=1;
 for(let i=0;i<5;i++){let yy=pad.t+i*(h-pad.t-pad.b)/4;x.beginPath();x.moveTo(pad.l,yy);x.lineTo(w-pad.r,yy);x.stroke();x.fillStyle="#7895b2";x.font="9px Arial";x.fillText((hi-(hi-lo)*i/4).toFixed(2),w-pad.r+5,yy+3);}
 rows.forEach((c,i)=>{const xx=pad.l+i*step+step/2,up=c.close>=c.open,col=up?"#00e99a":"#ff456b";x.strokeStyle=col;x.fillStyle=col;x.beginPath();x.moveTo(xx,y(c.high));x.lineTo(xx,y(c.low));x.stroke();x.fillRect(xx-bw/2,Math.min(y(c.open),y(c.close)),bw,Math.max(1,Math.abs(y(c.open)-y(c.close))));});
 const last=rows[rows.length-1],yy=y(last.close);x.strokeStyle="#16cfff";x.setLineDash([3,4]);x.beginPath();x.moveTo(pad.l,yy);x.lineTo(w-pad.r,yy);x.stroke();x.setLineDash([]);
 x.fillStyle="#16cfff";x.fillRect(w-pad.r+2,yy-8,48,16);x.fillStyle="#02101d";x.font="bold 9px Arial";x.fillText(last.close.toFixed(2),w-pad.r+4,yy+3);
 visiblePositions.forEach(p=>{
  const lines=[["ENTRY",Number(p.open_price),"#f3c969"],["SL",Number(p.stop_loss),"#ff456b"],["TP",Number(p.take_profit),"#00e99a"]];
  lines.forEach(item=>{
   if(!Number.isFinite(item[1])||item[1]<=0)return;
   const yy2=y(item[1]);x.strokeStyle=item[2];x.setLineDash([5,4]);x.beginPath();x.moveTo(pad.l,yy2);x.lineTo(w-pad.r,yy2);x.stroke();x.setLineDash([]);
   x.fillStyle=item[2];x.font="bold 9px Arial";x.fillText(item[0]+" "+item[1].toFixed(2),w-pad.r+4,yy2-3);
  });
  x.fillStyle="#dcecff";x.font="9px Arial";
  x.fillText(p.side+" "+p.lots+"L · P/L "+Number(p.profit||0).toFixed(2),pad.l+4,12);
 });
}
async function refresh(){
 if(busy)return;busy=true;
 try{
  setState("FETCHING MARKET");
  const m=await get("/api/deriv/markets?category=forex");
  const match=(m.markets||[]).find(v=>label(v.symbol).toUpperCase()===symbol);
  if(!match){marketSymbol=null;lastCandles=[];draw([]);setState("XAUUSD NOT IN FEED");if(note)note.textContent="The current public Forex feed did not return XAUUSD. A broker-connected MT4 feed is required for verified Gold candles and positions. No substitute symbol will be shown as Gold.";if(priceEl)priceEl.textContent="—";return;}
  marketSymbol=match.symbol;
  const d=await get("/api/deriv/candles/"+encodeURIComponent(marketSymbol)+"?granularity="+granularity+"&count=100");
  lastCandles=(d.candles||[]).map(c=>({open:Number(c.open??c.o),high:Number(c.high??c.h),low:Number(c.low??c.l),close:Number(c.close??c.c)})).filter(c=>[c.open,c.high,c.low,c.close].every(Number.isFinite));
  try{
   const bridge=await get("/api/mt4/positions");
   mt4Positions=bridge.connected?(bridge.positions||[]):[];
  }catch(error){mt4Positions=[];}
  draw(lastCandles);
  const latest=lastCandles.at(-1)?.close;
  if(priceEl)priceEl.textContent=Number.isFinite(latest)?latest.toFixed(3):"—";
  setState(mt4Positions.some(p=>p.symbol===symbol)?"MT4 POSITION OVERLAY":"PUBLIC MARKET DATA");
  if(note)note.textContent=mt4Positions.some(p=>p.symbol===symbol)
   ?"Entry, stop-loss, take-profit and floating P/L lines are sourced from the connected JustMarkets MT4 demo account. Candle background remains the public Deriv feed."
   :"Public Forex candles are shown. MT4 entry, stop-loss, take-profit and P/L overlays appear when the connected Expert Advisor reports a matching open position.";
 }catch(e){setState("FEED UNAVAILABLE");draw([]);if(note)note.textContent=e.message+" No trade has been placed.";}
 finally{busy=false;}
}
$("mt4-chart-symbol")?.addEventListener("change",e=>{symbol=e.target.value;refresh();});
$("mt4-chart-timeframe")?.addEventListener("change",e=>{granularity=Number(e.target.value);refresh();});
window.addEventListener("resize",()=>draw(lastCandles));
refresh();
setInterval(refresh,30000);
})();