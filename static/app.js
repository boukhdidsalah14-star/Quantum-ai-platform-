(()=> {
const $=id=>document.getElementById(id);
const pairs=[
 {symbol:"frxEURUSD",label:"EUR / USD",flag:"🇪🇺🇺🇸"},
 {symbol:"frxGBPUSD",label:"GBP / USD",flag:"🇬🇧🇺🇸"},
 {symbol:"frxUSDJPY",label:"USD / JPY",flag:"🇺🇸🇯🇵"},
 {symbol:"frxAUDUSD",label:"AUD / USD",flag:"🇦🇺🇺🇸"},
 {symbol:"frxUSDCAD",label:"USD / CAD",flag:"🇺🇸🇨🇦"},
 {symbol:"frxUSDCHF",label:"USD / CHF",flag:"🇺🇸🇨🇭"},
 {symbol:"frxNZDUSD",label:"NZD / USD",flag:"🇳🇿🇺🇸"},
 {symbol:"frxEURJPY",label:"EUR / JPY",flag:"🇪🇺🇯🇵"},
 {symbol:"frxGBPJPY",label:"GBP / JPY",flag:"🇬🇧🇯🇵"},
 {symbol:"frxXAUUSD",label:"XAU / USD",flag:"🥇🇺🇸"}
];
const binaryPairs=[
 {symbol:"frxEURUSD",label:"EUR / USD",flag:"🇪🇺🇺🇸"},
 {symbol:"frxGBPUSD",label:"GBP / USD",flag:"🇬🇧🇺🇸"},
 {symbol:"frxUSDJPY",label:"USD / JPY",flag:"🇺🇸🇯🇵"},
 {symbol:"frxAUDUSD",label:"AUD / USD",flag:"🇦🇺🇺🇸"},
 {symbol:"frxUSDCHF",label:"USD / CHF",flag:"🇺🇸🇨🇭"},
 {symbol:"frxUSDCAD",label:"USD / CAD",flag:"🇺🇸🇨🇦"},
 {symbol:"frxEURJPY",label:"EUR / JPY",flag:"🇪🇺🇯🇵"},
 {symbol:"frxGBPJPY",label:"GBP / JPY",flag:"🇬🇧🇯🇵"}
];
let selected=pairs[0], selectedBinary=binaryPairs[0], marketMap={}, chartCandles=[], member=false, signed=false, history=[];
const safe=(s)=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money=n=>Number(n).toLocaleString("en-US",{maximumFractionDigits:5});
function toast(t){$("toast").textContent=t;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),2500)}
function nav(page){document.querySelectorAll(".page").forEach(p=>p.classList.toggle("active",p.dataset.page===page));document.querySelectorAll("[data-nav]").forEach(b=>b.classList.toggle("active",b.dataset.nav===page));window.scrollTo({top:0,behavior:"smooth"})}
document.querySelectorAll("[data-nav]").forEach(b=>b.addEventListener("click",()=>nav(b.dataset.nav)));
document.querySelectorAll("[data-goto]").forEach(b=>b.addEventListener("click",()=>nav(b.dataset.goto)));
$("top-signin").addEventListener("click",()=>nav("account"));$("top-account").addEventListener("click",()=>nav("account"));
function setSelected(p){selected=p; $("home-pair").value=p.symbol;$("chart-title").textContent=p.label;if(binaryPairs.some(x=>x.symbol===p.symbol)){selectedBinary=p;$("signal-pair-title").textContent=p.label;renderPairList()}loadChart()}
function renderPairList(){ $("pair-list").innerHTML=binaryPairs.map(p=>'<button class="pair-item '+(p.symbol===selectedBinary.symbol?'active':'')+'" data-pair="'+p.symbol+'"><span class="flag">'+p.flag+'</span><span><b>'+p.label+'</b><small>Binary Options · Forex</small></span><span class="pair-price">'+(marketMap[p.symbol]?.price?money(marketMap[p.symbol].price):"—")+'</span></button>').join("");document.querySelectorAll("[data-pair]").forEach(b=>b.addEventListener("click",()=>{selectedBinary=binaryPairs.find(p=>p.symbol===b.dataset.pair);setSelected(pairs.find(p=>p.symbol===b.dataset.pair));$("signal-pair-title").textContent=selectedBinary.label;renderPairList()}))}
function renderTicker(){let items=pairs.map(p=>'<span>'+p.flag+' '+p.label+' <b>'+(marketMap[p.symbol]?.price?money(marketMap[p.symbol].price):"LIVE")+'</b></span>');items.push('<span>₿ BTC / USDT <b>USD-M FUTURES FEED</b></span>');$("ticker").innerHTML=items.concat(items).join("");}
async function loadMarkets(){try{let r=await fetch("/api/deriv/markets?category=forex");if(!r.ok)throw Error("Forex feed unavailable");let d=await r.json();marketMap={};(d.markets||[]).forEach(m=>marketMap[m.symbol]=m);renderPairList();renderTicker();$("feed-label").textContent="BINARY OPTIONS · INDEPENDENT FOREX FEED";}catch(e){$("ticker").innerHTML="<span>LIVE FOREX FEED TEMPORARILY UNAVAILABLE</span>";$("feed-label").textContent="Feed unavailable"}}
const cryptoAssets=["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","TRXUSDT","DOGEUSDT","ADAUSDT","BCHUSDT","LINKUSDT"];
$("crypto-symbol").innerHTML=cryptoAssets.map(s=>'<option value="'+s+'">'+s.replace("USDT","")+' / USDT</option>').join("");
async function loadCryptoMarkets(){
 try{
  const response=await fetch("/api/markets");
  if(!response.ok)throw Error("Futures market feed unavailable");
  const data=await response.json();
  const rows=new Map((data.markets||[]).map(item=>[item.symbol,item]));
  $("crypto-market-list").innerHTML=cryptoAssets.map(symbol=>{
   const item=rows.get(symbol);
   const price=item?money(Number(item.price)):"—";
   const change=item?Number(item.change_percent):0;
   return '<button class="pair-item" data-crypto-symbol="'+symbol+'"><span class="flag">₿</span><span><b>'+symbol.replace("USDT","")+'</b><small>USD-M perpetual · '+(item?((change>=0?"+":"")+change.toFixed(2)+"%"):"feed unavailable")+'</small></span><span class="pair-price">'+price+'</span></button>';
  }).join("");
  document.querySelectorAll("[data-crypto-symbol]").forEach(button=>button.addEventListener("click",()=>{
   $("crypto-symbol").value=button.dataset.cryptoSymbol;
  }));
 }catch(error){
  $("crypto-market-list").innerHTML="<p class='muted'>Crypto futures feed temporarily unavailable.</p>";
 }
}
let cryptoCandles=[];
function drawCryptoChart(){
 const canvas=$("crypto-price-chart"),box=canvas.parentElement;
 const width=box.clientWidth,height=box.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
 canvas.width=width*dpr;canvas.height=height*dpr;
 const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
 ctx.strokeStyle="#0b3153";ctx.lineWidth=1;
 for(let i=1;i<5;i++){const y=height*i/5;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}
 if(!cryptoCandles.length){ctx.fillStyle="#7998b7";ctx.font="12px Inter";ctx.fillText("Waiting for futures candles…",16,height/2);return;}
 const low=Math.min(...cryptoCandles.map(c=>Number(c.low))),high=Math.max(...cryptoCandles.map(c=>Number(c.high))),span=high-low||1;
 const step=width/cryptoCandles.length,body=Math.max(2,step*.52);
 cryptoCandles.forEach((c,i)=>{
  const x=i*step+step/2,open=height-(Number(c.open)-low)/span*height*.86-height*.07,close=height-(Number(c.close)-low)/span*height*.86-height*.07;
  const top=height-(Number(c.high)-low)/span*height*.86-height*.07,bottom=height-(Number(c.low)-low)/span*height*.86-height*.07;
  const rising=Number(c.close)>=Number(c.open);ctx.strokeStyle=rising?"#00e99a":"#ff456b";ctx.fillStyle=ctx.strokeStyle;
  ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();
  ctx.fillRect(x-body/2,Math.min(open,close),body,Math.max(2,Math.abs(close-open)));
 });
}
async function loadCryptoChart(){
 try{
  const symbol=$("crypto-symbol").value,interval=$("crypto-timeframe").value;
  const response=await fetch("/api/candles/"+encodeURIComponent(symbol)+"?interval="+encodeURIComponent(interval)+"&limit=100");
  if(!response.ok)throw Error("Futures candles unavailable");
  const data=await response.json();cryptoCandles=data.candles||[];drawCryptoChart();
 }catch(error){cryptoCandles=[];drawCryptoChart();}
}
$("crypto-symbol").addEventListener("change",loadCryptoChart);
$("crypto-timeframe").addEventListener("change",loadCryptoChart);
window.addEventListener("resize",drawCryptoChart);
async function runCryptoAnalysis(){
 if(!signed||!member){nav("account");toast("Sign in and activate membership to generate analysis");return;}
 const symbol=$("crypto-symbol").value;
 const timeframe=$("crypto-timeframe").value;
 const result=$("crypto-signal-result");
 const detail=$("crypto-signal-details");
 result.className="signal-result idle";
 result.innerHTML="<div class='signal-arrow'>⌁</div><b>ANALYSING "+safe(symbol)+"…</b><small>Fetching completed MEXC USD-M futures candles</small>";
 try{
  const response=await fetch("/api/signals/crypto/"+encodeURIComponent(symbol)+"?timeframe="+encodeURIComponent(timeframe));
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Crypto analysis unavailable");
  const direction=data.trade_bias||"WAIT";
  result.className="signal-result "+(direction==="LONG"?"call":direction==="SHORT"?"put":"idle");
  result.innerHTML="<div class='signal-arrow'>"+(direction==="LONG"?"↗":direction==="SHORT"?"↘":"Ⅱ")+"</div><b>"+direction+"</b><small>"+safe(symbol)+" · "+safe(timeframe)+" · "+safe(data.signal_strength)+" confidence</small>";
  detail.hidden=false;
  detail.innerHTML="<b>MEXC USD-M · ANALYSIS DETAILS</b><br>Trend: "+safe(data.trend)+" · RSI(14): "+safe(data.rsi_14)+" · ADX(14): "+safe(data.adx_14)+" · ATR(14): "+safe(data.atr_14)+"<br>EMA 9/21/50: "+safe(data.ema_9)+" / "+safe(data.ema_21)+" / "+safe(data.ema_50)+"<br>MACD: "+safe(data.macd)+" · Signal: "+safe(data.macd_signal)+"<br>Bollinger upper/mid/lower: "+safe(data.bollinger_upper)+" / "+safe(data.bollinger_middle)+" / "+safe(data.bollinger_lower)+"<br>Volume ratio: "+safe(data.volume_ratio_20??"unavailable")+"<br>"+(data.reasons||[]).map(safe).join(" · ")+"<br><small>Research signal only. It does not place a futures order or guarantee a profitable result.</small>";
 }catch(error){
  result.className="signal-result idle";
  result.innerHTML="<b>NO SIGNAL</b><small>"+safe(error.message)+"</small>";
 }
}
$("crypto-analyze").addEventListener("click",runCryptoAnalysis);
async function runCryptoPaperEntry(){
 if(!signed||!member){nav("account");toast("Sign in and activate membership to use paper auto-entry");return;}
 const button=$("crypto-paper-entry"),output=$("crypto-paper-result");
 const balance=Number($("crypto-paper-balance").value),risk=Number($("crypto-paper-risk").value),leverage=Number($("crypto-paper-leverage").value);
 if(!Number.isFinite(balance)||balance<=0||!Number.isFinite(risk)||risk<=0||risk>1||!Number.isInteger(leverage)||leverage<1||leverage>20){toast("Use a positive balance, risk up to 1%, and leverage from 1x to 20x");return;}
 button.disabled=true;button.textContent="CHECKING SIGNAL…";output.hidden=false;output.textContent="Checking completed MEXC futures candles and risk limits…";
 try{
  const key=(window.crypto&&window.crypto.randomUUID)?window.crypto.randomUUID():"qai-"+Date.now()+"-"+Math.random().toString(16).slice(2);
  const response=await fetch("/api/paper/crypto/auto",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":key},body:JSON.stringify({symbol:$("crypto-symbol").value,timeframe:$("crypto-timeframe").value,account_balance:balance,risk_percent:risk,leverage})});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Paper entry unavailable");
  if(!data.created){output.textContent="NO PAPER ENTRY · "+(data.reason||"No qualifying high-confidence signal");toast("No entry: signal filter says wait");return;}
  const trade=data.trade,plan=data.plan;
  output.innerHTML="<b>PAPER POSITION OPENED · "+safe(plan.side.toUpperCase())+"</b><br>"+safe(trade.symbol)+" · Entry "+money(plan.entry_price)+" · Qty "+Number(plan.quantity).toFixed(6)+"<br>Stop "+money(plan.stop_loss)+" · Target "+money(plan.take_profit)+"<br>Notional "+money(plan.notional_usdt)+" USDT · Margin est. "+money(plan.margin_required_usdt)+" USDT · Risk "+Number(plan.risk_percent).toFixed(2)+"% · "+Number(plan.leverage)+"×<br><small>Simulated only. No MEXC order was sent.</small>";
  toast("Paper position created");
 }catch(error){output.textContent="PAPER ENTRY FAILED · "+error.message;toast(error.message);}
 finally{button.disabled=false;button.textContent="AUTO PAPER ENTRY";}
}
$("crypto-paper-entry").addEventListener("click",runCryptoPaperEntry);
async function loadChart(){try{let tf=$("home-timeframe").value;let gran={"5m":300,"15m":900,"1h":3600,"4h":14400,"1d":86400}[tf];let r=await fetch("/api/deriv/candles/"+encodeURIComponent(selected.symbol)+"?granularity="+gran+"&count=80");if(!r.ok)throw Error("Chart unavailable");let d=await r.json();chartCandles=d.candles||[];let last=chartCandles.at(-1);$("current-price").textContent=last?money(last.close):"—";drawChart();}catch(e){chartCandles=[];drawChart();$("current-price").textContent="—";}}
function drawChart(){let c=$("price-chart"),box=c.parentElement,w=box.clientWidth,h=box.clientHeight,dpr=Math.min(devicePixelRatio||1,2);c.width=w*dpr;c.height=h*dpr;let x=c.getContext("2d");x.scale(dpr,dpr);x.clearRect(0,0,w,h);x.strokeStyle="#0b3153";x.lineWidth=1;for(let i=1;i<5;i++){let y=h*i/5;x.beginPath();x.moveTo(0,y);x.lineTo(w,y);x.stroke()}if(!chartCandles.length){x.fillStyle="#7998b7";x.font="12px Inter";x.fillText("Waiting for live candle data…",16,h/2);return}let lo=Math.min(...chartCandles.map(v=>+v.low)),hi=Math.max(...chartCandles.map(v=>+v.high)),span=hi-lo||1,step=w/chartCandles.length,bw=Math.max(2,step*.52);chartCandles.forEach((v,i)=>{let cx=i*step+step/2,yo=h-(v.open-lo)/span*h*.86-h*.07,yc=h-(v.close-lo)/span*h*.86-h*.07,yh=h-(v.high-lo)/span*h*.86-h*.07,yl=h-(v.low-lo)/span*h*.86-h*.07,up=v.close>=v.open;x.strokeStyle=up?"#00e99a":"#ff456b";x.fillStyle=x.strokeStyle;x.beginPath();x.moveTo(cx,yh);x.lineTo(cx,yl);x.stroke();x.fillRect(cx-bw/2,Math.min(yo,yc),bw,Math.max(2,Math.abs(yc-yo)));});}
window.addEventListener("resize",drawChart);
$("home-pair").innerHTML=pairs.map(p=>'<option value="'+p.symbol+'">'+p.flag+" "+p.label+'</option>').join("");$("floating-pair").innerHTML=binaryPairs.map(p=>'<option value="'+p.symbol+'">'+p.flag+" "+p.label+'</option>').join("");
$("home-pair").addEventListener("change",e=>setSelected(pairs.find(p=>p.symbol===e.target.value)));$("home-timeframe").addEventListener("change",loadChart);
async function refreshAuth(){try{let r=await fetch("/api/auth/me");if(!r.ok)throw Error();let d=await r.json();signed=true;$("auth-form-wrap").hidden=true;$("signed-in-panel").hidden=false;$("member-email").textContent=d.customer.email;$("account-chip").textContent="MEMBER";$("top-signin").textContent="ACCOUNT";let sr=await fetch("/api/subscription");let s=await sr.json();member=!!(sr.ok&&s.active);$("auth-state").textContent=member?"ACTIVE":"UNPAID";$("membership-status").textContent=member?"ACTIVE MEMBERSHIP":"NOT ACTIVE";$("membership-status").classList.toggle("active",member);$("membership-expiry").textContent=member?(s.days_remaining+" days remaining · expires "+new Date(s.expires_at*1000).toLocaleDateString()):"Subscribe for $20 USDT TRC20 / 30 days."; $("checkout-button").disabled=!s.payment_configured||member;$("checkout-button").textContent=member?"MEMBERSHIP ACTIVE":s.payment_configured?"SUBSCRIBE · $20 USDT TRC20":"PAYMENT SETUP PENDING";$("home-membership").textContent=member?"ACTIVE":"UNPAID";$("home-membership-note").textContent=member?"Trading access enabled":"Subscribe to unlock trading";$("auth-message").textContent=member?"Membership confirmed. Paid features are unlocked.":"You can browse the app. Trading actions are locked until payment confirmation.";}catch{signed=false;member=false;$("auth-form-wrap").hidden=false;$("signed-in-panel").hidden=true;$("account-chip").textContent="GUEST";$("auth-state").textContent="GUEST";$("home-membership").textContent="GUEST ACCESS";$("home-membership-note").textContent="Sign in to manage access";$("membership-status").textContent="NOT ACTIVE";let c=await fetch("/api/auth/config").then(r=>r.json()).catch(()=>({}));$("signup-button").hidden=!c.registration_enabled;$("auth-message").textContent=c.registration_enabled?"Sign in or create an account.":"Sign in to your account. Registration is currently closed.";}}
$("auth-form").addEventListener("submit",async e=>{e.preventDefault();let b=$("signin-button");b.disabled=true;try{let r=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("auth-email").value,password:$("auth-password").value})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Sign in failed");$("auth-password").value="";await refreshAuth();toast("Signed in successfully");}catch(e){$("auth-message").textContent=e.message;}$("signin-button").disabled=false});
$("signup-button").addEventListener("click",async()=>{try{let r=await fetch("/api/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("auth-email").value,password:$("auth-password").value})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Registration failed");$("auth-password").value="";await refreshAuth();toast("Account created");}catch(e){$("auth-message").textContent=e.message}});
$("signout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});$("payment-box").hidden=true;await refreshAuth();toast("Signed out")});
$("checkout-button").addEventListener("click",async()=>{let b=$("checkout-button");b.disabled=true;try{let r=await fetch("/api/subscription/checkout",{method:"POST"});let d=await r.json();if(!r.ok)throw Error(d.detail||"Checkout failed");$("pay-amount").textContent=d.pay_amount+" USDT";$("pay-address").textContent=d.pay_address;$("payment-box").hidden=false;toast("Payment request created");}catch(e){toast(e.message)}finally{b.disabled=false}});
$("copy-address").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("pay-address").textContent);toast("Address copied")}catch{toast("Select and copy the address")}});
async function generateSignal(pair,container,detail){if(!signed||!member){nav("account");toast("Sign in and activate the $20 membership first");return}container.className="signal-result idle";container.innerHTML="<div class='signal-arrow'>⌁</div><b>ANALYSING BINARY OPTIONS…</b><small>Fetching completed Forex candles</small>";try{let tf=$("signal-timeframe").value;let r=await fetch("/api/signals/deriv/"+encodeURIComponent(pair.symbol)+"?category=forex&timeframe="+tf);let d=await r.json();if(!r.ok)throw Error(d.detail||"Signal unavailable");let dir=d.direction||"WAIT";container.className="signal-result "+(dir==="CALL"?"call":dir==="PUT"?"put":"idle");container.innerHTML="<div class='signal-arrow'>"+(dir==="CALL"?"↗":dir==="PUT"?"↘":"Ⅱ")+"</div><b>"+dir+"</b><small>"+safe(pair.label)+" · "+safe(tf)+" · "+safe(d.signal_strength||"low")+" confidence</small>";detail.hidden=false;detail.innerHTML="<b>BINARY OPTIONS · Analysis details</b><br>Trend: "+safe(d.trend)+" · RSI(14): "+safe(d.rsi_14)+" · Score: "+safe(d.score)+"<br>Reference close: "+safe(d.last_close)+"<br>"+(d.reasons||[]).map(safe).join(" · ")+"<br><small>Indicator result only. It does not place a trade or guarantee a win.</small>";let t={pair:pair.label,dir,time: new Date().toLocaleTimeString(),tf};history.unshift(t);history=history.slice(0,12);renderHistory();$("floating-result").textContent="BINARY OPTIONS · "+pair.label+" · "+dir+" · "+tf; if(container===$("signal-result"))$("signal-feed").textContent="BINARY OPTIONS · FRESH";}catch(e){container.className="signal-result idle";container.innerHTML="<b>NO SIGNAL</b><small>"+safe(e.message)+"</small>";}}
function renderHistory(){$("signal-history").innerHTML=history.length?history.map(h=>'<div class="history-item"><span><b>'+safe(h.pair)+'</b><small> · '+safe(h.tf)+' · '+safe(h.time)+'</small></span><b style="color:'+(h.dir==="CALL"?"#00e99a":h.dir==="PUT"?"#ff456b":"#a8c8e4")+'">'+safe(h.dir)+'</b></div>').join(""):"<p class='muted'>No signals generated yet.</p>"}
$("get-signal").addEventListener("click",()=>generateSignal(selectedBinary,$("signal-result"),$("signal-details")));
$("floating-signal").addEventListener("click",()=>generateSignal(binaryPairs.find(p=>p.symbol===$("floating-pair").value)||binaryPairs[0],$("floating-result"),{set hidden(v){},set innerHTML(v){}}));
$("floating-open").addEventListener("click",()=>$("floating-window").hidden=false);$("floating-close").addEventListener("click",()=>$("floating-window").hidden=true);
let drag=null;$("floating-head").addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY,left:$("floating-window").offsetLeft,top:$("floating-window").offsetTop};$("floating-head").setPointerCapture(e.pointerId)});$("floating-head").addEventListener("pointermove",e=>{if(!drag)return;let el=$("floating-window");el.style.left=Math.max(4,drag.left+e.clientX-drag.x)+"px";el.style.top=Math.max(75,drag.top+e.clientY-drag.y)+"px";el.style.right="auto";el.style.bottom="auto"});$("floating-head").addEventListener("pointerup",()=>drag=null);
const providerInfo={
 mt4:["JustMarkets MT4 bridge","A demo-only MQL4 Expert Advisor is available for your JustMarkets desktop MT4 terminal. Register your demo login and exact server in the MT4 panel, copy the one-time bridge token into the EA inputs, then enable WebRequest for this app's HTTPS domain. Android MT4 cannot run Expert Advisors. Real-account execution is disabled; demo order execution also stays locked until durable storage and the server-side demo switch are configured."],
 mexc:["MEXC account integration (locked)","The current public MEXC market-data adapter is spot-only. MEXC futures order execution is not connected to customer accounts. API-key verification, encrypted storage, order reconciliation, independent risk checks and an emergency stop must be completed before any live integration."],
 deriv:["Deriv binary options","The app has public Forex candles and signal analysis. Deriv demo execution exists in the backend behind separate storage and kill-switch gates. Connect and verify your own VRTC demo account only after the service is configured; real-account execution remains disabled."]
};
function openProvider(k){$("modal-title").textContent=providerInfo[k][0];$("modal-copy").textContent=providerInfo[k][1];$("provider-modal").hidden=false}
document.querySelectorAll("[data-provider]").forEach(b=>b.addEventListener("click",()=>openProvider(b.dataset.provider)));$("modal-close").addEventListener("click",()=>$("provider-modal").hidden=true);$("modal-ok").addEventListener("click",()=>$("provider-modal").hidden=true);$("provider-modal").addEventListener("click",e=>{if(e.target===$("provider-modal"))$("provider-modal").hidden=true});
$("signal-timeframe").addEventListener("change",()=>{let v=$("signal-timeframe").value;if(["1","5","15","30","60"].includes(v))$("signal-expiry").value=v});
loadMarkets().then(()=>{setSelected(selected);refreshAuth().then(()=>{refreshMt4Bridge();loadMt4Orders();refreshMt4Auto()})});loadCryptoMarkets();loadCryptoChart();setInterval(loadMarkets,30000);setInterval(loadCryptoMarkets,30000);setInterval(loadCryptoChart,30000);setInterval(()=>{if($("page-home").classList.contains("active"))loadChart()},60000);
if(window.Telegram?.WebApp){window.Telegram.WebApp.ready();window.Telegram.WebApp.expand()}

const swipePages=["home","signals","automation","account"];
let touchX=null,touchY=null;
$("main").addEventListener("touchstart",e=>{if(e.touches.length===1){touchX=e.touches[0].clientX;touchY=e.touches[0].clientY}},{passive:true});
$("main").addEventListener("touchend",e=>{if(touchX===null)return;let dx=e.changedTouches[0].clientX-touchX,dy=e.changedTouches[0].clientY-touchY;touchX=touchY=null;if(Math.abs(dx)>65&&Math.abs(dx)>Math.abs(dy)*1.25){let active=swipePages.findIndex(p=>$("page-"+p).classList.contains("active"));let next=Math.max(0,Math.min(swipePages.length-1,active+(dx<0?1:-1)));if(next!==active)nav(swipePages[next])}},{passive:true});


async function refreshMt4Bridge(){
 const badge=$("mt4-bridge-status");
 if(!signed){badge.textContent="SIGN IN";$("mt4-bridge-account").textContent="—";$("mt4-bridge-balance").textContent="—";$("mt4-bridge-equity").textContent="—";return;}
 try{
  const response=await fetch("/api/mt4/bridge/status",{cache:"no-store"});
  if(!response.ok)throw Error("Bridge status unavailable");
  const data=await response.json();
  badge.textContent=data.connected?"CONNECTED":data.registered?"EA OFFLINE":"NOT REGISTERED";
  $("mt4-bridge-account").textContent=data.account_login||"—";
  $("mt4-bridge-balance").textContent=data.balance==null?"—":money(data.balance)+" "+(data.currency||"");
  $("mt4-bridge-equity").textContent=data.equity==null?"—":money(data.equity)+" "+(data.currency||"");
  $("mt4-connection-state").textContent=data.connected?"JUSTMARKETS DEMO · CONNECTED":"NOT CONNECTED";
  $("mt4-open-position").textContent=data.connected?(data.positions.length+" OPEN"): "NONE REPORTED";
  const pnl=data.connected?data.positions.reduce((sum,p)=>sum+Number(p.profit||0)+Number(p.swap||0)+Number(p.commission||0),0):null;
  $("mt4-open-pnl").textContent=pnl==null?"—":money(pnl)+" "+(data.currency||"");
  if(data.connected){
   $("mt4-bridge-message").textContent="JustMarkets MT4 demo terminal is connected. Position and quote snapshots are being refreshed.";
  }else if(data.registered){
   $("mt4-bridge-message").textContent="Bridge token registered for "+data.account_server+". Open the JustMarkets MT4 terminal and attach the EA to reconnect.";
  }else{
   $("mt4-bridge-message").textContent="Register your JustMarkets MT4 demo account above. No broker password is requested or stored.";
  }
 }catch(error){badge.textContent="STATUS UNAVAILABLE";}
}
async function loadMt4Orders(){
 if(!signed)return;
 try{
  const response=await fetch("/api/mt4/orders",{cache:"no-store"});
  if(!response.ok)return;
  const data=await response.json();
  const orders=data.orders||[];
  $("mt4-order-history").innerHTML=orders.length?orders.map(o=>'<div class="history-row"><b>'+safe(o.symbol)+' '+safe(o.side)+'</b><span>'+safe(o.lots)+' lots · '+safe(o.status.toUpperCase())+'</span><small>SL '+safe(o.stop_loss)+' · TP '+safe(o.take_profit)+(o.broker_ticket?' · Ticket '+safe(o.broker_ticket):'')+'</small></div>').join(""):"<p class='muted'>No MT4 commands yet.</p>";
 }catch(error){}
}

async function refreshMt4Auto(){
 const badge=$("mt4-auto-status"),message=$("mt4-auto-message");
 if(!signed){badge.textContent="SIGN IN";message.textContent="Sign in to configure your JustMarkets demo auto trader.";return;}
 try{
  const response=await fetch("/api/mt4/auto",{cache:"no-store"});
  if(!response.ok)throw Error("Auto-trader status unavailable");
  const data=await response.json();
  badge.textContent=data.active?"RUNNING · DEMO":"STOPPED";
  $("mt4-auto-symbol").value=data.symbol||"XAUUSD";
  $("mt4-auto-timeframe").value=data.timeframe||"15m";
  $("mt4-auto-lots").value=data.lots||0.01;
  $("mt4-auto-drawdown").value=data.max_drawdown_pct||10;
  $("mt4-auto-stop-atr").value=data.stop_atr||1.5;
  $("mt4-auto-target-atr").value=data.target_atr||2;
  message.textContent=data.last_message||"Demo-only auto trader is stopped.";
  $("mt4-auto-start").disabled=!data.server_execution_enabled;
  if(!data.server_execution_enabled)message.textContent="The MT4 demo execution safety switch is currently off. Real-account execution is not available.";
 }catch(error){badge.textContent="STATUS UNAVAILABLE";message.textContent=error.message;}
}
$("mt4-bridge-form").addEventListener("submit",async e=>{
 e.preventDefault();
 if(!signed){nav("account");toast("Sign in first to register your MT4 bridge");return;}
 const button=e.submitter||$("mt4-bridge-form").querySelector("button[type=submit]");
 button.disabled=true;
 try{
  const response=await fetch("/api/mt4/bridge/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_login:$("mt4-account-login").value.trim(),account_server:$("mt4-account-server").value.trim()})});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not register the MT4 bridge");
  $("mt4-bridge-token").textContent=data.bridge_token;
  $("mt4-bridge-token-box").hidden=false;
  $("mt4-bridge-message").textContent="Bridge token created. Copy it once, download the EA, and configure the EA inputs in your JustMarkets MT4 demo terminal.";
  toast("MT4 demo bridge token created");
  refreshMt4Bridge();
 }catch(error){toast(error.message);}
 finally{button.disabled=false;}
});
$("mt4-copy-token").addEventListener("click",async()=>{
 const value=$("mt4-bridge-token").textContent;
 try{await navigator.clipboard.writeText(value);toast("Bridge token copied");}
 catch(error){const field=document.createElement("textarea");field.value=value;document.body.appendChild(field);field.select();document.execCommand("copy");field.remove();toast("Bridge token copied");}
});

$("mt4-auto-form").addEventListener("submit",async e=>{
 e.preventDefault();
 if(!signed){nav("account");toast("Sign in first to configure auto trading");return;}
 if(!member){nav("account");toast("Active membership required for auto trading");return;}
 const button=$("mt4-auto-start");button.disabled=true;
 try{
  const payload={symbol:$("mt4-auto-symbol").value,timeframe:$("mt4-auto-timeframe").value,lots:Number($("mt4-auto-lots").value),max_drawdown_pct:Number($("mt4-auto-drawdown").value),stop_atr:Number($("mt4-auto-stop-atr").value),target_atr:Number($("mt4-auto-target-atr").value)};
  const response=await fetch("/api/mt4/auto/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not start demo auto trader");
  toast("JustMarkets demo auto trader started");
  refreshMt4Auto();
 }catch(error){$("mt4-auto-message").textContent=error.message;toast(error.message);}
 finally{button.disabled=false;}
});
$("mt4-auto-stop").addEventListener("click",async()=>{
 if(!signed){nav("account");toast("Sign in first");return;}
 const button=$("mt4-auto-stop");button.disabled=true;
 try{
  const response=await fetch("/api/mt4/auto/stop",{method:"POST"});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not stop auto trader");
  toast("Auto trader stopped. Pending auto entries cancelled; an already delivered MT4 command may still execute.");
  refreshMt4Auto();
 }catch(error){toast(error.message);}
 finally{button.disabled=false;}
});
$("mt4-demo-order-form").addEventListener("submit",async e=>{
 e.preventDefault();
 if(!signed){nav("account");toast("Sign in first");return;}
 if(!member){nav("account");toast("Active membership required for demo order requests");return;}
 const button=$("mt4-demo-order-submit");button.disabled=true;
 try{
  const payload={symbol:$("mt4-order-symbol").value,side:$("mt4-order-side").value,lots:Number($("mt4-order-lots").value),stop_loss:Number($("mt4-order-sl").value),take_profit:Number($("mt4-order-tp").value)};
  const response=await fetch("/api/mt4/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Demo order was not queued");
  toast("Demo order queued. Waiting for the connected MT4 EA.");
  loadMt4Orders();
 }catch(error){toast(error.message);}
 finally{button.disabled=false;}
});
setInterval(()=>{refreshMt4Bridge();loadMt4Orders();refreshMt4Auto()},10000);

async function refreshMetaTraderConnection(){
 const platform=$("mt-cloud-platform").value;
 const state=$("mt-cloud-state"),note=$("mt-cloud-note"),result=$("mt-cloud-result");
 try{
  const response=await fetch("/api/connections/metatrader/"+encodeURIComponent(platform));
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Connection status unavailable");
  state.textContent=data.connected?"CONNECTED":(data.state||"NOT CONNECTED");
  note.textContent=data.connected
   ? "Cloud terminal connected. Trading remains locked until the demo execution tests and account risk controls are completed."
   : "Cloud account status: "+(data.state||"not configured")+" · "+(data.connection_status||"waiting for secure account setup");
  if(result.hidden===false&&!data.connected) result.hidden=false;
 }catch(error){state.textContent="STATUS UNAVAILABLE";note.textContent=error.message;}
}
$("mt-cloud-form")?.addEventListener("submit",async event=>{
 event.preventDefault();
 const button=$("mt-cloud-connect"),result=$("mt-cloud-result"),state=$("mt-cloud-state");
 const payload={platform:$("mt-cloud-platform").value,broker:$("mt-cloud-broker").value.trim(),server:$("mt-cloud-server").value.trim()};
 button.disabled=true;button.textContent="CREATING CLOUD CONNECTION…";
 try{
  const response=await fetch("/api/connections/metatrader",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not create cloud connection");
  result.hidden=false;
  result.replaceChildren();
  const heading=document.createElement("b");heading.textContent=payload.platform.toUpperCase()+" CLOUD ACCOUNT CREATED";result.appendChild(heading);
  const status=document.createElement("p");status.textContent="State: "+(data.state||"DRAFT")+". Complete the secure broker login on MetaApi.";result.appendChild(status);
  const link=document.createElement("a");link.href=data.configuration_link;link.target="_blank";link.rel="noopener noreferrer";link.textContent="OPEN SECURE META TRADER ACCOUNT SETUP";result.appendChild(link);
  const detail=document.createElement("small");detail.textContent="This one-time setup link expires in 24 hours. QUANTUM AI does not receive or store your MetaTrader password.";result.appendChild(detail);
  state.textContent="SETUP REQUIRED";toast("Cloud account created. Finish secure setup.");
 }catch(error){result.hidden=false;result.textContent=error.message;state.textContent="NOT CONNECTED";toast(error.message);}
 finally{button.disabled=false;button.textContent="CREATE SECURE CLOUD CONNECTION";}
});
$("mt-cloud-refresh")?.addEventListener("click",refreshMetaTraderConnection);
$("mt-cloud-platform")?.addEventListener("change",refreshMetaTraderConnection);
$("mt-cloud-disconnect")?.addEventListener("click",async()=>{
 const platform=$("mt-cloud-platform").value;
 if(!window.confirm("Disconnect the "+platform.toUpperCase()+" cloud account?"))return;
 try{
  const response=await fetch("/api/connections/metatrader/"+encodeURIComponent(platform),{method:"DELETE"});
  const data=await response.json();if(!response.ok)throw Error(data.detail||"Disconnect failed");
  $("mt-cloud-result").hidden=true;$("mt-cloud-state").textContent="DISCONNECTED";$("mt-cloud-note").textContent="Cloud account disconnected.";
  toast(data.deleted?"Account disconnected":"No account was registered");
 }catch(error){toast(error.message);}
});
})();