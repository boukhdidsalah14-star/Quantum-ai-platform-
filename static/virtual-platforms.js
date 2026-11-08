(()=> {
const $=id=>document.getElementById(id),fmt=n=>"$"+Number(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}),labels={binary:"BINARY",forex:"FOREX",crypto:"CRYPTO"},latestPrices={},quotes={},seen=new Set();let baselineLoaded=false,lastCandles=null,depthSymbol="";
async function api(url,options={}){const r=await fetch(url,{...options,headers:{"Content-Type":"application/json",...(options.headers||{})}}),b=await r.json();if(!r.ok)throw new Error(b.detail||"Request failed");return b}
function key(s){return String(s||"").toUpperCase().replace(/^FRX/,"").replace("/","")}
function renderAccounts(accounts){for(const [p,a] of Object.entries(accounts||{})){const bal=$("v-"+p+"-balance"),risk=$("v-"+p+"-risk");if(bal)bal.textContent=fmt(a.balance);if(risk)risk.textContent=fmt(a.remaining_loss_allowance)+" remaining";const available=$("bn-available");if(p==="crypto"&&available)available.textContent=fmt(a.balance);if(p==="forex"){const eq=$("mt4-equity"),m=$("mt4-margin");if(eq)eq.textContent=fmt(a.balance);if(m)m.textContent=fmt(a.balance);}}}}
function safe(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function renderHistory(platform,rows){const el=$("v-"+platform+"-history");if(!el)return;const open=rows.filter(x=>x.status==="open").length,count=$(platform+"-open-count");if(count)count.textContent=String(open);el.innerHTML=rows.length?rows.map(t=>{const pnl=t.pnl===null?"OPEN":fmt(t.pnl),expired=platform!=="binary"||Date.now()/1000>=Number(t.created_at)+Number(t.expiry_minutes||0)*60,close=t.status==="open"?"<button class='tf virtual-close' data-id='"+safe(t.id)+"' data-platform='"+platform+"' data-symbol='"+safe(t.symbol)+"' "+(expired?"":"disabled")+">"+(expired?"CLOSE AT LIVE QUOTE":"EXPIRES "+new Date((Number(t.created_at)+Number(t.expiry_minutes)*60)*1000).toLocaleTimeString())+"</button>":"";return "<article class='virtual-position'><div><b>"+safe(t.symbol)+"</b><br>"+safe(t.side)+" · "+fmt(t.stake)+"</div><div>Entry "+Number(t.entry_price)+"<br>"+(t.exit_price===null?"Open position":"Exit "+Number(t.exit_price))+"</div><div class='"+(Number(t.pnl)>=0?"positive":"negative")+"'>"+pnl+"<br>"+safe(t.result||t.status).toUpperCase()+"</div>"+close+"</article>"}).join(""):"<p class='disclaimer'>No positions yet. Your trades will appear here.</p>";}
function selectedSymbol(p){const sel=$('[data-terminal-symbol="'+p+'"]');return sel?.value||""}
function syncFormSymbol(p,s){const form=document.querySelector('.virtual-form[data-platform="'+p+'"]');if(form?.elements.symbol)form.elements.symbol.value=s}
function selectMarket(p,s){const platform=p==="crypto"?"crypto":"forex";if(window.QUANTUM_SELECT_MARKET)window.QUANTUM_SELECT_MARKET({platform,symbol:s,timeframe:p==="crypto"?"1h":"15m"}).catch(()=>{});}
function onMarkets(d){
 if(!d||!Array.isArray(d.markets))return;
 const fx=d.markets.filter(x=>d.source?.startsWith("deriv_")&&x.market==="forex"&&x.symbol);
 if(fx.length){
  document.querySelectorAll('select[data-market-kind="forex"]').forEach(sel=>{
   const old=sel.value;
   sel.innerHTML=fx.map(x=>"<option value='"+safe(x.symbol)+"'>"+safe(x.name||x.symbol)+"</option>").join("");
   if(fx.some(x=>x.symbol===old))sel.value=old;
   const p=sel.dataset.terminalSymbol;if(p)syncFormSymbol(p,sel.value);
  });
  const watch=document.querySelector(".mt4-watch");
  if(watch){
   const head=watch.querySelector(".watch-head");
   watch.querySelectorAll(".watch-row").forEach(x=>x.remove());
   fx.slice(0,12).forEach(item=>{
    const row=document.createElement("div");
    row.className="watch-row"+(item.symbol===selectedSymbol("forex")?" selected":"");
    row.dataset.symbol=item.symbol;
    row.innerHTML="<b>"+safe(item.symbol.replace(/^frx/i,""))+"</b><span>"+(item.price==null?"—":Number(item.price).toFixed(5))+"</span>";
    row.addEventListener("click",()=>{
     const sel=document.querySelector('select[data-terminal-symbol="forex"]');
     if(sel){sel.value=item.symbol;sel.dispatchEvent(new Event("change",{bubbles:true}));}
    });
    if(head)head.after(row);
   });
  }
 }
}
function onMarket(d){if(!d?.symbol||!Number.isFinite(Number(d.price)))return;latestPrices[d.symbol]=Number(d.price);const k=key(d.symbol);for(const form of document.querySelectorAll(".virtual-form")){const p=form.dataset.platform,field=form.elements.symbol,price=form.elements.entry_price;if(!field||!price)continue;const match=p==="crypto"?field.value===d.symbol:k===key(field.value);if(match){price.value=String(Number(d.price));price.dataset.quoteAt=String(Date.now());price.dataset.quoteSymbol=d.symbol;const target=p==="crypto"?"crypto":p;const out=$(target+"-chart-price");if(out)out.textContent=fmt(d.price);const name=$(target+"-chart-name");if(name)name.textContent=d.symbol.replace("frx","").replace("USDT"," / USDT").replace(/([A-Z]{3})([A-Z]{3})/,"$1/$2");if(p==="forex"){const bid=$("mt4-bid"),ask=$("mt4-ask"),os=$("mt4-order-symbol");if(bid)bid.textContent=Number(d.price).toFixed(5);if(ask)ask.textContent="—";if(os)os.textContent=key(d.symbol);}if(p==="crypto"){const bp=$("bn-book-price");if(bp)bp.textContent=fmt(d.price);loadBinanceDepth(d.symbol);}}}}}
function drawChart(canvasId,d){const c=$(canvasId);if(!c||!d?.candles?.length)return;const ctx=c.getContext("2d"),w=c.clientWidth,h=c.clientHeight,dpr=window.devicePixelRatio||1;c.width=Math.max(1,w*dpr);c.height=Math.max(1,h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);const a=d.candles.slice(-70),lo=Math.min(...a.map(x=>Number(x.l))),hi=Math.max(...a.map(x=>Number(x.h))),range=hi-lo||1,pad={l:8,r:9,t:12,b:14},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b,y=v=>pad.t+(hi-v)/range*ch;ctx.strokeStyle="#173456";ctx.lineWidth=1;for(let i=0;i<5;i++){let yy=pad.t+ch*i/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke()}const step=cw/a.length,bw=Math.max(2,step*.58);a.forEach((x,i)=>{const up=Number(x.c)>=Number(x.o),col=up?"#42d99a":"#ff647c",xx=pad.l+i*step+step/2;ctx.strokeStyle=col;ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(xx,y(Number(x.h)));ctx.lineTo(xx,y(Number(x.l)));ctx.stroke();ctx.fillRect(xx-bw/2,y(Math.max(Number(x.o),Number(x.c))),bw,Math.max(1,Math.abs(y(Number(x.o))-y(Number(x.c)))))});ctx.fillStyle="#83a6ca";ctx.font="9px monospace";ctx.fillText("HIGH "+hi.toPrecision(7),10,10);ctx.fillText("LOW "+lo.toPrecision(7),10,h-3);}
function onCandles(d){
 if(!d?.candles)return;lastCandles=d;const sym=key(d.symbol);
 for(const p of ["binary","forex","crypto"]){const s=selectedSymbol(p);if(s&&key(s)===sym)drawChart(p+"-terminal-chart",d);}
}
async function loadBinanceDepth(symbol){
 if(!symbol||!symbol.endsWith("USDT")||depthSymbol===symbol+"-loading")return;
 depthSymbol=symbol+"-loading";
 try{
  const data=await api("/api/orderbook/"+encodeURIComponent(symbol)+"?limit=10");
  if(data.symbol!==selectedSymbol("crypto"))return;
  const render=(selector,rows,reverse)=>{
   const el=document.querySelector(selector);if(!el)return;
   const items=reverse?[...rows].reverse():rows;let total=0;
   el.innerHTML=items.slice(0,6).map(([price,qty])=>{
    total+=Number(qty);
    return "<div><span>"+Number(price).toFixed(Number(price)>100?2:4)+"</span><span>"+Number(qty).toFixed(4)+"</span><span>"+total.toFixed(4)+"</span></div>";
   }).join("");
  };
  render(".bn-book-rows.sell",data.asks,true);render(".bn-book-rows.buy",data.bids,false);
  const spread=document.querySelector(".bn-book-footer");
  if(spread)spread.textContent="Spread "+Number(data.spread).toFixed(Number(data.spread)>1?2:5);
  depthSymbol=symbol;
 }catch(e){
  const el=document.querySelector(".bn-book-footer");if(el)el.textContent="Order book unavailable";
  depthSymbol="";
 }
}
async function refresh(){try{const a=await api("/api/virtual/accounts");renderAccounts(a.accounts);for(const p of Object.keys(labels)){const t=await api("/api/virtual/"+p+"/positions");renderHistory(p,t.positions||[]);for(const row of t.positions||[]){if(!baselineLoaded){seen.add(row.id);continue;}if(row.status==="open"&&!seen.has(row.id)){seen.add(row.id);window.dispatchEvent(new CustomEvent("quantum:trade",{detail:{platform:p,symbol:row.symbol,side:row.side,timeframe:"15m",position:row,source:"ledger-poll"}}));}}}baselineLoaded=true;}catch(e){for(const p of Object.keys(labels)){const b=$("v-"+p+"-balance"),r=$("v-"+p+"-risk"),s=$("v-"+p+"-status");if(b)b.textContent="—";if(r)r.textContent="—";if(s)s.textContent=e.message.includes("Authentication")?"Sign in to access your private virtual account.":e.message;}}}

document.querySelectorAll("[data-binary-side]").forEach(btn=>btn.addEventListener("click",()=>{const form=btn.closest("form");if(form?.elements.side)form.elements.side.value=btn.dataset.binarySide;}));
document.querySelectorAll("[data-mt4-side]").forEach(btn=>btn.addEventListener("click",()=>{const form=btn.closest("form");if(!form)return;form.elements.side.value=btn.dataset.mt4Side;if(btn.dataset.mt4Side==="SELL")form.requestSubmit();}));
document.querySelectorAll(".bn-trade-tabs b").forEach((tab,i)=>tab.addEventListener("click",()=>{const form=tab.closest(".bn-trade").querySelector("form");form.elements.side.value=i===0?"BUY":"SELL";tab.parentElement.querySelectorAll("b").forEach((x,j)=>{x.style.color=j===i?(i===0?"#0ecb81":"#f6465d"):"#9aa4b2";x.style.borderBottom=j===i?"2px solid currentColor":"0";});const submit=form.querySelector(".bn-submit");submit.textContent=(i===0?"BUY ":"SELL ")+key(form.elements.symbol.value);submit.style.background=i===0?"#0ecb81":"#f6465d";}));
document.querySelectorAll(".bn-select-wrap select").forEach(sel=>sel.addEventListener("change",()=>{const btn=document.querySelector(".bn-submit");if(btn)btn.textContent=(document.querySelector('.bn-trade form [name="side"]').value==="BUY"?"BUY ":"SELL ")+key(sel.value);}));
document.querySelectorAll("[data-step]").forEach(btn=>btn.addEventListener("click",()=>{const input=btn.parentElement.querySelector('input[name="stake"]');if(input)input.value=String(Math.max(.01,Number(input.value||0)+Number(btn.dataset.step)));}));

document.querySelectorAll(".page-nav a[href^=\"#virtual-\"]").forEach(link=>link.addEventListener("click",ev=>{
 const targetId=link.getAttribute("href").slice(1),target=document.getElementById(targetId);
 const view=target?.dataset.terminalView,tab=view&&document.querySelector('.terminal-tab[data-terminal-tab="'+view+'"]');
 if(!target||!tab)return;
 ev.preventDefault();
 if(!tab.classList.contains("active"))tab.click();
 requestAnimationFrame(()=>target.scrollIntoView({behavior:"smooth",block:"start"}));
}));
document.querySelectorAll(".terminal-tab").forEach(b=>b.addEventListener("click",()=>{
 document.querySelectorAll(".terminal-tab").forEach(x=>x.classList.toggle("active",x===b));
 document.querySelectorAll(".terminal-view").forEach(x=>x.classList.toggle("active",x.dataset.terminalView===b.dataset.terminalTab));
 const p=b.dataset.terminalTab;selectMarket(p,selectedSymbol(p));
 requestAnimationFrame(()=>{if(lastCandles)onCandles(lastCandles);});
 if(p==="crypto")loadBinanceDepth(selectedSymbol("crypto"));
}));
document.querySelectorAll("[data-terminal-symbol]").forEach(sel=>sel.addEventListener("change",()=>{const p=sel.dataset.terminalSymbol;syncFormSymbol(p,sel.value);selectMarket(p,sel.value);}));
document.querySelectorAll("[data-sync-chart]").forEach(b=>b.addEventListener("click",()=>{const p=b.dataset.syncChart;selectMarket(p,selectedSymbol(p));document.querySelector("#markets")?.scrollIntoView({behavior:"smooth"});}));
document.querySelectorAll(".virtual-form").forEach(form=>{form.addEventListener("submit",async ev=>{ev.preventDefault();const p=form.dataset.platform,b=form.querySelector("button[type=submit]"),data=Object.fromEntries(new FormData(form).entries()),price=form.elements.entry_price,age=Date.now()-Number(price.dataset.quoteAt||0);if(!price.value||!Number.isFinite(Number(price.value))||age>45000||price.dataset.quoteSymbol!==data.symbol){$("v-"+p+"-status").textContent="Waiting for a fresh live quote. Select the market and try again.";selectMarket(p,data.symbol);return;}b.disabled=true;try{data.stake=Number(data.stake);data.entry_price=Number(price.value);data.expiry_minutes=Number(data.expiry_minutes||5);const r=await api("/api/virtual/"+p+"/positions",{method:"POST",headers:{"Idempotency-Key":"v-"+Date.now()+"-"+Math.random().toString(36).slice(2)},body:JSON.stringify(data)});$("v-"+p+"-status").textContent="VIRTUAL POSITION OPEN · "+data.symbol+" · "+data.side+" · Broker order not sent.";renderAccounts(r.accounts);seen.add(r.position.id);window.dispatchEvent(new CustomEvent("quantum:trade",{detail:{platform:p,symbol:data.symbol,side:data.side,timeframe:"15m",position:r.position}}));await refresh();}catch(e){$("v-"+p+"-status").textContent=e.message;}finally{b.disabled=false;}});});
document.addEventListener("click",async ev=>{const b=ev.target.closest(".virtual-close");if(!b)return;const p=b.dataset.platform,price=Object.entries(latestPrices).find(([s])=>key(s)===key(b.dataset.symbol))?.[1];if(!price){$("v-"+p+"-status").textContent="Select this market to obtain a fresh exit quote.";selectMarket(p,b.dataset.symbol);return;}b.disabled=true;try{const r=await api("/api/virtual/"+p+"/positions/"+encodeURIComponent(b.dataset.id)+"/settle",{method:"POST",body:JSON.stringify({exit_price:price})});renderAccounts(r.accounts);$("v-"+p+"-status").textContent="Virtual position settled · "+r.position.result.toUpperCase()+" · "+fmt(r.position.pnl)+" P/L.";await refresh();}catch(e){$("v-"+p+"-status").textContent=e.message;b.disabled=false;}});
window.addEventListener("quantum:markets",e=>onMarkets(e.detail));window.addEventListener("quantum:market",e=>onMarket(e.detail));window.addEventListener("quantum:candles",e=>onCandles(e.detail));
window.QUANTUM_SYNC_BOT_TRADE=detail=>window.dispatchEvent(new CustomEvent("quantum:trade",{detail:{...detail,source:"bot-bridge"}}));
const initial=selectedSymbol("binary");if(initial)selectMarket("binary",initial);
refresh();setInterval(refresh,8000);setInterval(()=>{if(selectedSymbol("crypto")){depthSymbol="";loadBinanceDepth(selectedSymbol("crypto"));}},5000);window.addEventListener("resize",()=>{if(lastCandles)requestAnimationFrame(()=>onCandles(lastCandles));});
})();