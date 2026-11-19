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
const referralFromUrl=new URLSearchParams(window.location.search).get("ref");if(referralFromUrl&&/^[A-Z0-9]{5,32}$/i.test(referralFromUrl))sessionStorage.setItem("quantum_referral_code",referralFromUrl.toUpperCase());
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
async function loadMarkets(){try{let r=await fetch("/api/market-data/forex/markets");if(!r.ok)throw Error("Forex feed unavailable");let d=await r.json();marketMap={};(d.markets||[]).forEach(m=>marketMap[m.symbol]=m);renderPairList();renderTicker();$("feed-label").textContent="BINARY OPTIONS · INDEPENDENT FOREX FEED";}catch(e){$("ticker").innerHTML="<span>LIVE FOREX FEED TEMPORARILY UNAVAILABLE</span>";$("feed-label").textContent="Feed unavailable"}}
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

async function refreshMexcAuto(){
 try{
  const [connection,strategy,live]=await Promise.all([
   fetch("/api/connections/mexc"),fetch("/api/mexc/futures/auto"),fetch("/api/mexc/futures/positions")
  ]);
  if(connection.ok){const c=await connection.json();$("mexc-connection-status").textContent=c.connected?"MEXC account connected · encrypted credentials stored":"MEXC account not connected";}
  if(strategy.ok){const d=await strategy.json(),v=d.strategy||{};$("mexc-auto-status").textContent=
   v.status==="active"?"AUTO TRADING ACTIVE · "+v.symbol+" · "+v.timeframe+" · "+v.risk_percent+"% risk · "+v.leverage+"×":
   v.status==="stopped"?"AUTO TRADING STOPPED"+(v.last_error?" · "+v.last_error:""):"AUTO TRADING NOT STARTED";}
  if(live.ok){
   const d=await live.json(),positions=d.positions||[],orders=d.open_orders||[];
   const positionHtml=positions.map(p=>'<div class="trade-row"><b>'+safe(p.symbol)+'</b><span>'+(Number(p.positionType)===1?'LONG':'SHORT')+' · '+safe(p.holdVol)+'</span><span>Entry '+money(p.holdAvgPrice)+' · P/L '+money(p.unRealizedPnl)+'</span></div>').join("");
   const orderHtml=orders.map(o=>'<div class="trade-row"><b>'+safe(o.symbol)+'</b><span>OPEN ORDER · '+safe(o.side)+'</span><span>'+safe(o.vol)+' contracts</span></div>').join("");
   $("mexc-live-positions").innerHTML=(positionHtml||'<small>No open MEXC Futures positions.</small>')+(orderHtml||"");
  }else if(live.status===409){$("mexc-live-positions").textContent="Connect MEXC to view live positions.";}

 }catch(e){$("mexc-auto-status").textContent="MEXC status unavailable";}
}
async function connectMexcAccount(){
 if(!signed){nav("account");toast("Sign in first to connect your MEXC account");return;}
 const apiKey=$("mexc-api-key").value.trim(),apiSecret=$("mexc-api-secret").value;
 if(!apiKey||!apiSecret){toast("Enter both MEXC API credentials");return;}
 const button=$("mexc-connect");button.disabled=true;button.textContent="VERIFYING…";
 try{
  const r=await fetch("/api/connections/mexc/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key:apiKey,api_secret:apiSecret})});
  const d=await r.json();if(!r.ok)throw Error(d.detail||"MEXC verification failed");
  $("mexc-connection-status").textContent=d.credential_saved?"MEXC Futures account verified · credentials encrypted":"Account verified, but secure persistent storage is not ready";
  $("mexc-api-key").value="";$("mexc-api-secret").value="";toast("MEXC account verified");
 }catch(e){$("mexc-connection-status").textContent="CONNECTION FAILED · "+e.message;toast(e.message);}
 finally{button.disabled=false;button.textContent="VERIFY & SAVE";}
}
async function startMexcAuto(){
 if(!signed||!member){nav("account");toast("Sign in and activate membership first");return;}
 const button=$("mexc-auto-start"),output=$("mexc-auto-status");
 button.disabled=true;button.textContent="STARTING…";
 try{
  const r=await fetch("/api/mexc/futures/auto/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   symbol:$("crypto-symbol").value,timeframe:$("crypto-timeframe").value,
   risk_percent:Number($("crypto-paper-risk").value),leverage:Number($("crypto-paper-leverage").value)
  })});
  const d=await r.json();if(!r.ok)throw Error(d.detail||"Could not start MEXC auto trading");
  output.textContent="AUTO TRADING ACTIVE · "+d.strategy.symbol+" · "+d.strategy.timeframe;
  toast("MEXC futures auto trading started");
 }catch(e){output.textContent="AUTO TRADING NOT STARTED · "+e.message;toast(e.message);}
 finally{button.disabled=false;button.textContent="START LIVE AUTO TRADING";await refreshMexcAuto();}
}
async function stopMexcAuto(){
 const button=$("mexc-auto-stop");button.disabled=true;
 try{
  const r=await fetch("/api/mexc/futures/auto/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
  const d=await r.json();if(!r.ok)throw Error(d.detail||"Could not stop auto trading");
  $("mexc-auto-status").textContent="AUTO TRADING STOPPED · Existing exchange positions remain protected by their TP/SL";
  toast("New MEXC auto entries stopped");
 }catch(e){toast(e.message);}
 finally{button.disabled=false;await refreshMexcAuto();}
}
$("mexc-connect").addEventListener("click",connectMexcAccount);
$("mexc-auto-start").addEventListener("click",startMexcAuto);
$("mexc-auto-stop").addEventListener("click",stopMexcAuto);

let chartEmptyMessage="Market candles are temporarily unavailable.";
async function loadChart(){
 const tf=$("home-timeframe").value;
 const source=$("chart-source");
 try{
  const r=await fetch("/api/connections/ctrader/candles/"+encodeURIComponent(selected.symbol)+"?timeframe="+encodeURIComponent(tf)+"&count=80");
  const d=await r.json();
  if(!r.ok)throw Error(d.detail||"IC Markets cTrader chart unavailable");
  if(!Array.isArray(d.candles)||!d.candles.length)throw Error("cTrader returned no candles");
  chartCandles=d.candles;chartEmptyMessage="No recent candles were returned by cTrader.";
  if(source)source.textContent="IC MARKETS · cTRADER";
 }catch(ctraderError){
  try{
   const granularity={"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400}[tf]||900;
   const r=await fetch("/api/market-data/forex/candles/"+encodeURIComponent(selected.symbol)+"?granularity="+granularity+"&count=80");
   const d=await r.json();
   if(!r.ok)throw Error(d.detail||"Public market fallback unavailable");
   chartCandles=Array.isArray(d.candles)?d.candles:[];
   if(!chartCandles.length)throw Error("No fallback candles returned");
   chartEmptyMessage="Market candles are temporarily unavailable.";
   if(source)source.textContent="PUBLIC FOREX DATA · NOT IC MARKETS";
  }catch(fallbackError){
   chartCandles=[];chartEmptyMessage="Chart unavailable. Reconnect IC Markets cTrader or try again later.";
   if(source)source.textContent="MARKET DATA UNAVAILABLE";
  }
 }
 const last=chartCandles.at(-1);$("current-price").textContent=last?money(last.close):"—";drawChart();
}
function drawChart(){let c=$("price-chart"),box=c.parentElement,w=box.clientWidth,h=box.clientHeight,dpr=Math.min(devicePixelRatio||1,2);c.width=w*dpr;c.height=h*dpr;let x=c.getContext("2d");x.scale(dpr,dpr);x.clearRect(0,0,w,h);x.strokeStyle="#0b3153";x.lineWidth=1;for(let i=1;i<5;i++){let y=h*i/5;x.beginPath();x.moveTo(0,y);x.lineTo(w,y);x.stroke()}if(!chartCandles.length){x.fillStyle="#7998b7";x.font="12px Inter";x.fillText(chartEmptyMessage,16,h/2);return}let lo=Math.min(...chartCandles.map(v=>+v.low)),hi=Math.max(...chartCandles.map(v=>+v.high)),span=hi-lo||1,step=w/chartCandles.length,bw=Math.max(2,step*.52);chartCandles.forEach((v,i)=>{let cx=i*step+step/2,yo=h-(v.open-lo)/span*h*.86-h*.07,yc=h-(v.close-lo)/span*h*.86-h*.07,yh=h-(v.high-lo)/span*h*.86-h*.07,yl=h-(v.low-lo)/span*h*.86-h*.07,up=v.close>=v.open;x.strokeStyle=up?"#00e99a":"#ff456b";x.fillStyle=x.strokeStyle;x.beginPath();x.moveTo(cx,yh);x.lineTo(cx,yl);x.stroke();x.fillRect(cx-bw/2,Math.min(yo,yc),bw,Math.max(2,Math.abs(yc-yo)));});}
window.addEventListener("resize",drawChart);
$("home-pair").innerHTML=pairs.map(p=>'<option value="'+p.symbol+'">'+p.flag+" "+p.label+'</option>').join("");$("floating-pair").innerHTML=binaryPairs.map(p=>'<option value="'+p.symbol+'">'+p.flag+" "+p.label+'</option>').join("");
$("home-pair").addEventListener("change",e=>setSelected(pairs.find(p=>p.symbol===e.target.value)));$("home-timeframe").addEventListener("change",loadChart);
async function refreshAuth(){try{let r=await fetch("/api/auth/me");if(!r.ok)throw Error();let d=await r.json();signed=true;$("auth-form-wrap").hidden=true;$("signed-in-panel").hidden=false;$("member-email").textContent=d.customer.email;$("account-chip").textContent="MEMBER";$("top-signin").textContent="ACCOUNT";let sr=await fetch("/api/subscription");let s=await sr.json();member=!!(sr.ok&&s.active);$("auth-state").textContent=member?"ACTIVE":"UNPAID";$("membership-status").textContent=member?"ACTIVE MEMBERSHIP":"NOT ACTIVE";$("membership-status").classList.toggle("active",member);$("membership-expiry").textContent=member?(s.days_remaining+" days remaining · expires "+new Date(s.expires_at*1000).toLocaleDateString()):"Subscribe for $30 USDT TRC20 / 30 days."; $("checkout-button").disabled=!s.payment_configured||member;$("checkout-button").textContent=member?"MEMBERSHIP ACTIVE":s.payment_configured?"SUBSCRIBE · $30 USDT TRC20":"PAYMENT SETUP PENDING";$("home-membership").textContent=member?"ACTIVE":"UNPAID";$("home-membership-note").textContent=member?"Trading access enabled":"Subscribe to unlock trading";$("auth-message").textContent=member?"Membership confirmed. Paid features are unlocked.":"You can browse the app. Trading actions are locked until payment confirmation.";await loadPendingPayment();await loadReferralDashboard();await loadSignalHistory();await refreshCTraderStatus();}catch{signed=false;member=false;$("auth-form-wrap").hidden=false;$("signed-in-panel").hidden=true;$("account-chip").textContent="GUEST";$("auth-state").textContent="GUEST";$("home-membership").textContent="GUEST ACCESS";$("home-membership-note").textContent="Sign in to manage access";$("membership-status").textContent="NOT ACTIVE";let c=await fetch("/api/auth/config").then(r=>r.json()).catch(()=>({}));$("signup-button").hidden=!c.registration_enabled;$("auth-message").textContent=c.registration_enabled?"Sign in or create an account.":"Sign in to your account. Registration is currently closed.";}}
async function loadReferralDashboard(){
 const link=$("referral-link");if(!link)return;
 if(!signed){link.textContent="Sign in to generate your personal link";$("referral-state").textContent="SIGN IN";return;}
 try{const r=await fetch("/api/referrals");const d=await r.json();if(!r.ok)throw Error(d.detail||"Referral data unavailable");link.textContent=d.link;link.dataset.url=d.link;$("referral-signups").textContent=d.signups+" / 8";$("referral-paid").textContent=d.paid_referrals+" / 2";$("referral-state").textContent=d.reward_eligible?"REWARD READY":"TRACKING";$("referral-progress").textContent=d.reward_eligible?"Congratulations! Your free month is being applied.":"You need "+d.signups_to_next_reward+" more sign-ups and "+d.paid_to_next_reward+" more paid customer(s) to unlock your next free month.";$("referral-history").textContent=d.rewards.length?d.rewards.map(x=>"30 days · "+new Date(x.granted_at*1000).toLocaleDateString()).join(" | "):"No free months earned yet.";}catch(e){$("referral-state").textContent="UNAVAILABLE";$("referral-progress").textContent=e.message;}
}
$("referral-copy")?.addEventListener("click",async()=>{const url=$("referral-link").dataset.url;if(!url){toast("Sign in first to get your invite link");return;}try{await navigator.clipboard.writeText(url);toast("Invite link copied");}catch{toast(url);}});
$("referral-share")?.addEventListener("click",async()=>{const url=$("referral-link").dataset.url;if(!url){toast("Sign in first to get your invite link");return;}const data={title:"Join QUANTUM AI",text:"Try QUANTUM AI. Sign up with my invite link:",url};try{if(navigator.share)await navigator.share(data);else{await navigator.clipboard.writeText(data.text+" "+url);toast("Invite message copied");}}catch(e){if(e.name!=="AbortError")toast("Sharing is unavailable on this device");}});
async function loadPendingPayment(){
 const box=$("payment-box");
 if(!signed||member){box.hidden=true;return;}
 try{
  const response=await fetch("/api/subscription/order");
  const data=await response.json();
  const order=data.order;
  if(!response.ok||!order||!order.payment_id){box.hidden=true;return;}
  $("pay-amount").textContent=order.pay_amount+" USDT";
  $("pay-address").textContent=order.pay_address||"—";
  $("pay-id").textContent=order.payment_id;
  $("pay-order-id").textContent=order.order_id;
  $("payment-status").textContent=String(order.payment_status||"waiting").toUpperCase();
  box.hidden=false;
 }catch(error){box.hidden=true;}
}
async function refreshPaymentStatus(){
 const button=$("refresh-payment-status");
 button.disabled=true;button.textContent="CHECKING…";
 try{
  const response=await fetch("/api/subscription/refresh",{method:"POST"});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not verify payment");
  if(data.subscription&&data.subscription.active){
   toast("Payment confirmed · membership activated");
   await refreshAuth();
   return;
  }
  const status=data.payment?.payment_status||data.result?.status||"pending";
  $("payment-status").textContent=String(status).toUpperCase();
  await loadPendingPayment();
  toast("Payment status: "+status);
 }catch(error){toast(error.message);}
 finally{button.disabled=false;button.textContent="CHECK PAYMENT STATUS";}
}
$("refresh-payment-status").addEventListener("click",refreshPaymentStatus);
$("auth-form").addEventListener("submit",async e=>{e.preventDefault();let b=$("signin-button");b.disabled=true;try{let r=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("auth-email").value,password:$("auth-password").value})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Sign in failed");$("auth-password").value="";await refreshAuth();toast("Signed in successfully");}catch(e){$("auth-message").textContent=e.message;}$("signin-button").disabled=false});
$("signup-button").addEventListener("click",async()=>{try{let r=await fetch("/api/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("auth-email").value,password:$("auth-password").value,referral_code:sessionStorage.getItem("quantum_referral_code")||""})});let d=await r.json();if(!r.ok)throw Error(d.detail||"Registration failed");sessionStorage.removeItem("quantum_referral_code");$("auth-password").value="";await refreshAuth();toast("Account created");}catch(e){$("auth-message").textContent=e.message}});
$("signout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});$("payment-box").hidden=true;await refreshAuth();toast("Signed out")});
$("checkout-button").addEventListener("click",async()=>{let b=$("checkout-button");b.disabled=true;try{let r=await fetch("/api/subscription/checkout",{method:"POST"});let d=await r.json();if(!r.ok)throw Error(d.detail||"Checkout failed");$("pay-amount").textContent=d.pay_amount+" USDT";$("pay-address").textContent=d.pay_address;$("pay-id").textContent=d.payment_id||"—";$("pay-order-id").textContent=d.order_id||"—";$("payment-status").textContent=String(d.payment_status||"waiting").toUpperCase();$("payment-box").hidden=false;toast("Payment request created");}catch(e){toast(e.message)}finally{b.disabled=false}});
$("copy-address").addEventListener("click",async()=>{try{await navigator.clipboard.writeText($("pay-address").textContent);toast("Address copied")}catch{toast("Select and copy the address")}});
async function generateSignal(pair,container,detail){
 if(!signed||!member){nav("account");toast("Sign in and activate the $30 membership first");return}
 container.className="signal-result idle";container.innerHTML="<div class='signal-arrow'>⌁</div><b>ANALYSING BINARY OPTIONS…</b><small>Fetching completed Forex candles</small>";
 try{
  const tf=$("signal-timeframe").value;const r=await fetch("/api/signals/forex/"+encodeURIComponent(pair.symbol)+"?timeframe="+tf);const d=await r.json();if(!r.ok)throw Error(d.detail||"Signal unavailable");
  const dir=d.direction||"WAIT";container.className="signal-result "+(dir==="CALL"?"call":dir==="PUT"?"put":"idle");
  container.innerHTML="<div class='signal-arrow'>"+(dir==="CALL"?"↗":dir==="PUT"?"↘":"Ⅱ")+"</div><b>"+dir+"</b><small>"+safe(pair.label)+" · "+safe(tf)+" · "+safe(d.signal_strength||"low")+" confidence</small>";
  detail.hidden=false;detail.innerHTML="<b>BINARY OPTIONS · Analysis details</b><br>Trend: "+safe(d.trend)+" · RSI(14): "+safe(d.rsi_14)+" · Score: "+safe(d.score)+"<br>Reference close: "+safe(d.last_close)+"<br>"+(d.reasons||[]).map(safe).join(" · ")+"<br><small>Indicator result only. It does not place a trade or guarantee a win.</small>";
  if(container===$("signal-result"))$("signal-feed").textContent="BINARY OPTIONS · FRESH";
  $("floating-result").textContent="BINARY OPTIONS · "+pair.label+" · "+dir+" · "+tf;
  await loadSignalHistory();
 }catch(e){container.className="signal-result idle";container.innerHTML="<b>NO SIGNAL</b><small>"+safe(e.message)+"</small>";}
}
function renderHistory(signals,stats){
 const list=$("signal-history");if(!list)return;
 const rate=stats.win_rate_pct===null?"—":stats.win_rate_pct+"%";
 const summary='<div class="history-stats"><span><small>TOTAL</small><b>'+stats.total+'</b></span><span><small>WINS</small><b>'+stats.wins+'</b></span><span><small>LOSSES</small><b>'+stats.losses+'</b></span><span><small>WIN RATE*</small><b>'+rate+'</b></span></div>';
 const rows=signals.map(s=>'<div class="history-item"><span><b>'+safe(s.symbol)+'</b><small> · '+safe(s.category)+' · '+safe(s.timeframe)+' · '+new Date(s.generated_at*1000).toLocaleString()+'</small><small> · '+safe(s.direction)+' / '+safe(s.strength)+'</small></span><span class="history-actions">'+(s.result?'<b>'+safe(s.result)+'</b>':s.direction!=="WAIT"?'<button class="outline-btn history-result-btn" data-history-id="'+safe(s.id)+'" data-result="WIN">WIN</button><button class="outline-btn history-result-btn" data-history-id="'+safe(s.id)+'" data-result="LOSS">LOSS</button><button class="outline-btn history-result-btn" data-history-id="'+safe(s.id)+'" data-result="DRAW">DRAW</button>':'<b>—</b>')+'</span></div>').join("");
 list.innerHTML=summary+(rows||"<p class='muted'>No saved signals yet. Generate a signal while signed in to build your history.</p>")+'<small class="risk-note">*Win rate uses only manually confirmed WIN and LOSS outcomes; draws and pending signals are excluded. Results are user-reported, not broker-verified.</small>';
}
async function loadSignalHistory(){
 if(!signed){$("signal-history").innerHTML="<p class='muted'>Sign in to view your saved signal history.</p>";return;}
 try{const r=await fetch("/api/signals/history");const d=await r.json();if(!r.ok)throw Error(d.detail||"History unavailable");renderHistory(d.signals||[],d.statistics||{total:0,wins:0,losses:0,win_rate_pct:null});}
 catch(e){$("signal-history").innerHTML="<p class='muted'>"+safe(e.message)+"</p>";}
}
$("signal-history").addEventListener("click",async e=>{
 const b=e.target.closest("[data-history-id]");if(!b)return;b.disabled=true;
 try{const r=await fetch("/api/signals/history/"+encodeURIComponent(b.dataset.historyId)+"/result",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({result:b.dataset.result})});const d=await r.json();if(!r.ok)throw Error(d.detail||"Could not save result");await loadSignalHistory();toast("Outcome saved as "+b.dataset.result);}
 catch(err){toast(err.message);b.disabled=false;}
});
$("get-signal").addEventListener("click",()=>generateSignal(selectedBinary,$("signal-result"),$("signal-details")));
$("floating-signal").addEventListener("click",()=>generateSignal(binaryPairs.find(p=>p.symbol===$("floating-pair").value)||binaryPairs[0],$("floating-result"),{set hidden(v){},set innerHTML(v){}}));$("floating-open").addEventListener("click",()=>$("floating-window").hidden=false);$("floating-close").addEventListener("click",()=>$("floating-window").hidden=true);
let drag=null;$("floating-head").addEventListener("pointerdown",e=>{drag={x:e.clientX,y:e.clientY,left:$("floating-window").offsetLeft,top:$("floating-window").offsetTop};$("floating-head").setPointerCapture(e.pointerId)});$("floating-head").addEventListener("pointermove",e=>{if(!drag)return;let el=$("floating-window");el.style.left=Math.max(4,drag.left+e.clientX-drag.x)+"px";el.style.top=Math.max(75,drag.top+e.clientY-drag.y)+"px";el.style.right="auto";el.style.bottom="auto"});$("floating-head").addEventListener("pointerup",()=>drag=null);
const providerInfo={
 mexc:["MEXC USD-M Futures account","Connect your own MEXC Futures API key. QUANTUM AI can verify account access, store credentials encrypted and run the selected futures strategy when the live-trading safety switch is enabled. Each entry is capped at 1% risk and $500 notional with exchange-side stop-loss and take-profit."],
 iq:["IQ Option · signals only","QUANTUM AI provides CALL / PUT / WAIT analysis for selected Forex pairs. IQ Option account authorization and broker order execution are not connected or enabled."]
};
function openProvider(k){$("modal-title").textContent=providerInfo[k][0];$("modal-copy").textContent=providerInfo[k][1];$("provider-modal").hidden=false}
document.querySelectorAll("[data-provider]").forEach(b=>b.addEventListener("click",()=>openProvider(b.dataset.provider)));$("modal-close").addEventListener("click",()=>$("provider-modal").hidden=true);$("modal-ok").addEventListener("click",()=>$("provider-modal").hidden=true);$("provider-modal").addEventListener("click",e=>{if(e.target===$("provider-modal"))$("provider-modal").hidden=true});
$("signal-timeframe").addEventListener("change",()=>{let v=$("signal-timeframe").value;if(["1","5","15","30","60"].includes(v))$("signal-expiry").value=v});
loadMarkets().then(()=>{setSelected(selected);refreshAuth().then(()=>{refreshMexcAuto()})});loadCryptoMarkets();loadCryptoChart();setInterval(loadMarkets,30000);setInterval(loadCryptoMarkets,30000);setInterval(loadCryptoChart,30000);setInterval(refreshMexcAuto,30000);setInterval(()=>{if($("page-home").classList.contains("active"))loadChart()},60000);
if(window.Telegram?.WebApp){window.Telegram.WebApp.ready();window.Telegram.WebApp.expand()}

const swipePages=["home","signals","automation","referrals","account"];
let touchX=null,touchY=null;
$("main").addEventListener("touchstart",e=>{if(e.touches.length===1){touchX=e.touches[0].clientX;touchY=e.touches[0].clientY}},{passive:true});
$("main").addEventListener("touchend",e=>{if(touchX===null)return;let dx=e.changedTouches[0].clientX-touchX,dy=e.changedTouches[0].clientY-touchY;touchX=touchY=null;if(Math.abs(dx)>65&&Math.abs(dx)>Math.abs(dy)*1.25){let active=swipePages.findIndex(p=>$("page-"+p).classList.contains("active"));let next=Math.max(0,Math.min(swipePages.length-1,active+(dx<0?1:-1)));if(next!==active)nav(swipePages[next])}},{passive:true});


async function refreshCTraderStatus(){
 const state=$("ctrader-state"),note=$("ctrader-note"),connect=$("ctrader-connect"),disconnect=$("ctrader-disconnect");
 if(!state||!note||!connect)return;
 try{
  const response=await fetch("/api/connections/ctrader/status");
  const data=await response.json();
  if(response.status===401){state.textContent="SIGN IN REQUIRED";note.textContent="Sign in to QUANTUM AI before connecting your broker account.";connect.disabled=false;connect.textContent="SIGN IN TO CONNECT";disconnect.hidden=true;return;}
  if(!response.ok)throw Error(data.detail||"Connection status unavailable");
  const snapshot=data.account_snapshot;
  state.textContent=snapshot?"DEMO ACCOUNT SYNCED":(data.authorized?"AUTHORISED · DEMO ACCOUNT REQUIRED":(data.configured?"NOT CONNECTED":"SETUP PENDING"));
  note.textContent=snapshot
   ?"IC Markets demo account is connected. You can place small manual demo orders with mandatory stop-loss and take-profit."
   :(data.authorized
    ?"Authorization is saved. Tap FIND DEMO ACCOUNTS, choose your IC Markets demo account, then sync it."
    :(data.configured
     ?"Authorize your IC Markets cTrader account. QUANTUM AI will sync a demo account before any trading feature is enabled."
     :"QUANTUM AI is waiting for its Spotware application credentials and approval."));
  connect.disabled=!data.configured;
  connect.textContent=data.authorized?"RECONNECT CTRADER":"CONNECT IC MARKETS CTRADER";
  disconnect.hidden=!data.authorized;
  const syncPanel=$("ctrader-account-sync");
  if(syncPanel)syncPanel.hidden=!data.authorized;
  if(snapshot)renderCTraderSnapshot(snapshot);
 }catch(error){state.textContent="STATUS UNAVAILABLE";note.textContent=error.message;}
}
async function loadCTraderRiskSettings(){
 const status=$("ctrader-risk-status");
 if(!status)return;
 try{
  const response=await fetch("/api/connections/ctrader/demo/risk");
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Risk settings unavailable");
  renderCTraderRiskStatus(data);
 }catch(error){status.textContent=error.message;}
}
function renderCTraderRiskStatus(data){
 const status=$("ctrader-risk-status");
 if(status){
  const loss=data.daily_loss_pct===null||data.daily_loss_pct===undefined?"Awaiting first daily balance snapshot":Number(data.daily_loss_pct).toFixed(2)+"% of starting balance";
  status.innerHTML="<b>SERVER RISK STATUS</b><br>Daily loss: "+safe(loss)+
   "<br>Daily starting balance: "+(data.daily_start_balance===null?"—":safe(Number(data.daily_start_balance).toFixed(2)))+
   "<br>Maximum size: "+safe(data.max_lots)+" lots · Max open positions: "+safe(data.max_open_positions)+
   "<br>Emergency stop: <b>"+(data.emergency_stop?"ACTIVE":"OFF")+"</b>"+
   "<br><small>Loss tracking: realized balance only · Limits enforced server-side</small>";
 }
 if($("ctrader-risk-loss"))$("ctrader-risk-loss").value=data.max_daily_loss_pct;
 if($("ctrader-risk-lots"))$("ctrader-risk-lots").value=data.max_lots;
 if($("ctrader-risk-positions"))$("ctrader-risk-positions").value=String(data.max_open_positions);
 const stop=$("ctrader-emergency-stop");
 if(stop){stop.dataset.active=data.emergency_stop?"true":"false";stop.textContent=data.emergency_stop?"RELEASE EMERGENCY STOP":"ACTIVATE EMERGENCY STOP";}
}
async function saveCTraderRiskSettings(){
 const button=$("ctrader-risk-save");
 button.disabled=true;button.textContent="SAVING…";
 try{
  const payload={
   max_daily_loss_pct:Number($("ctrader-risk-loss").value),
   max_lots:Number($("ctrader-risk-lots").value),
   max_open_positions:Number($("ctrader-risk-positions").value)
  };
  const response=await fetch("/api/connections/ctrader/demo/risk",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not save risk settings");
  renderCTraderRiskStatus(data);toast("Risk limits saved and enforced by the server");
 }catch(error){toast(error.message);}
 finally{button.disabled=false;button.textContent="SAVE RISK LIMITS";}
}
async function toggleCTraderEmergencyStop(){
 const button=$("ctrader-emergency-stop");
 const enabled=button.dataset.active!=="true";
 button.disabled=true;
 try{
  const response=await fetch("/api/connections/ctrader/demo/risk/emergency-stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled})});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not change emergency stop");
  renderCTraderRiskStatus(data);
  toast(enabled?"Emergency stop active: new entries blocked":"Emergency stop released");
 }catch(error){toast(error.message);}
 finally{button.disabled=false;}
}
async function loadCTraderCustomerAuthorization(){
 const panel=$("ctrader-customer-authorization");
 const status=$("ctrader-authorization-status");
 const form=$("ctrader-demo-order-form");
 if(!panel||!status)return;
 panel.hidden=false;
 try{
  const response=await fetch("/api/connections/ctrader/demo/authorization");
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Authorization status unavailable");
  const enabled=Boolean(data.demo_trading_authorized);
  status.innerHTML="<b>DEMO TRADING: "+(enabled?"AUTHORIZED":"NOT AUTHORIZED")+"</b>"+
   "<br>Selected account: "+(data.account_id?"#"+safe(data.account_id):"None")+
   "<br>Live trading: <b>LOCKED</b>";
  const button=$("ctrader-demo-auth-toggle");
  if(button)button.textContent=enabled?"REVOKE DEMO TRADING AUTHORIZATION":"AUTHORIZE DEMO TRADING";
  if(form)form.hidden=!enabled;
  if($("ctrader-demo-risk-ack"))$("ctrader-demo-risk-ack").checked=false;
 }catch(error){
  status.textContent=error.message;
  if(form)form.hidden=true;
 }
}
async function toggleCTraderCustomerAuthorization(){
 const button=$("ctrader-demo-auth-toggle");
 const currentlyEnabled=button.textContent.includes("REVOKE");
 const acknowledgement=$("ctrader-demo-risk-ack");
 if(!currentlyEnabled&&!acknowledgement?.checked){
  toast("Please confirm the demo-trading risk acknowledgement first");
  return;
 }
 button.disabled=true;
 try{
  const response=await fetch("/api/connections/ctrader/demo/authorization",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({
   enabled:!currentlyEnabled,acknowledge_risk:!currentlyEnabled&&Boolean(acknowledgement?.checked)
  })});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not update trading authorization");
  toast(data.demo_trading_authorized?"Demo trading authorization enabled for this account":"Demo trading authorization revoked");
  await loadCTraderCustomerAuthorization();
 }catch(error){toast(error.message);}
 finally{button.disabled=false;}
}
function renderCTraderSnapshot(snapshot){
 const box=$("ctrader-account-snapshot");
 if(!box||!snapshot)return;
 const positions=Array.isArray(snapshot.open_positions)?snapshot.open_positions:[];
 box.hidden=false;
 box.innerHTML="<b>IC MARKETS · DEMO ACCOUNT</b><br>Login: "+safe(snapshot.trader_login||"—")+
  "<br>Balance: <b>"+(Number.isFinite(Number(snapshot.balance))?Number(snapshot.balance).toFixed(2):"—")+"</b>"+
  "<br>Open positions: "+positions.length+" · Pending orders: "+safe(snapshot.pending_orders_count??0)+
  "<br><small>Broker sync · "+safe(new Date((snapshot.synced_at||0)*1000).toLocaleString())+"</small>"+
  (positions.length?"<hr>"+positions.map(p=>"<div class='ctrader-position-row'><b>"+safe(p.side)+"</b> · "+safe(p.symbol_id)+" · "+safe(p.volume_units)+" units · SL "+safe(p.stop_loss??"—")+" · TP "+safe(p.take_profit??"—")+"<br><small>Position #"+safe(p.position_id)+"</small><div class='chart-toolbar'><button type='button' class='outline-btn' data-ctrader-action='amend' data-position-id='"+safe(p.position_id)+"'>EDIT SL / TP</button><button type='button' class='outline-btn' data-ctrader-action='close' data-position-id='"+safe(p.position_id)+"'>CLOSE POSITION</button></div></div>").join(""):"<br><small>No open positions on this account.</small>")+
  "<br><small>Manual demo execution only · Max 0.01 lots per order.</small>";
 const tradePanel=$("ctrader-demo-trade");
 if(tradePanel)tradePanel.hidden=false;
 loadCTraderDemoSymbols();
 loadCTraderRiskSettings();
 loadCTraderCustomerAuthorization();
}
async function loadCTraderDemoSymbols(){
 const select=$("ctrader-order-symbol");
 if(!select)return;
 try{
  const response=await fetch("/api/connections/ctrader/markets");
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not load IC Markets demo symbols");
  const symbols=Array.isArray(data.markets)?data.markets.filter(x=>x.enabled):[];
  select.innerHTML='<option value="">Choose symbol</option>'+symbols.map(x=>'<option value="'+safe(x.symbol)+'">'+safe(x.symbol)+'</option>').join("");
 }catch(error){select.innerHTML='<option value="">Demo symbols unavailable</option>';toast(error.message);}
}
async function submitCTraderDemoOrder(event){
 event.preventDefault();
 const button=$("ctrader-open-demo");
 const payload={
  symbol:$("ctrader-order-symbol").value,
  side:$("ctrader-order-side").value,
  lots:Number($("ctrader-order-lots").value),
  stop_loss:Number($("ctrader-order-sl").value),
  take_profit:Number($("ctrader-order-tp").value)
 };
 button.disabled=true;button.textContent="SENDING TO BROKER…";
 try{
  const response=await fetch("/api/connections/ctrader/demo/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"cTrader demo order failed");
  if(!data.broker_confirmed)throw Error("No broker confirmation received");
  toast("cTrader confirmed the demo order request.");
  $("ctrader-order-sl").value="";$("ctrader-order-tp").value="";
  await refreshCTraderSnapshot();
 }catch(error){toast(error.message);}
 finally{button.disabled=false;button.textContent="PLACE DEMO ORDER";}
}
async function handleCTraderPositionAction(event){
 const button=event.target.closest("[data-ctrader-action]");
 if(!button)return;
 const positionId=button.dataset.positionId;
 if(button.dataset.ctraderAction==="close"){
  if(!window.confirm("Close this entire cTrader demo position?"))return;
  button.disabled=true;
  try{
   const response=await fetch("/api/connections/ctrader/demo/positions/close",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({position_id:positionId})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||"Position close failed");
   toast("Broker confirmed the close request.");await refreshCTraderSnapshot();
  }catch(error){toast(error.message);}finally{button.disabled=false;}
 }else if(button.dataset.ctraderAction==="amend"){
  const sl=window.prompt("New stop-loss price:");
  if(sl===null)return;
  const tp=window.prompt("New take-profit price:");
  if(tp===null)return;
  button.disabled=true;
  try{
   const response=await fetch("/api/connections/ctrader/demo/positions/protection",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({position_id:positionId,stop_loss:Number(sl),take_profit:Number(tp)})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||"Protection update failed");
   toast("Broker confirmed the SL/TP update.");await refreshCTraderSnapshot();
  }catch(error){toast(error.message);}finally{button.disabled=false;}
 }
}
async function discoverCTraderAccounts(){
 const button=$("ctrader-discover"),select=$("ctrader-account-select"),result=$("ctrader-result");
 if(!button||!select)return;
 button.disabled=true;button.textContent="SEARCHING…";
 try{
  const response=await fetch("/api/connections/ctrader/accounts");
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Could not discover cTrader demo accounts");
  const accounts=data.accounts||[];
  select.innerHTML='<option value="">Choose IC Markets demo account</option>'+accounts.map(a=>'<option value="'+safe(a.account_id)+'">'+safe(a.broker)+" · Login "+safe(a.trader_login||"—")+" · DEMO</option>").join("");
  if(result){result.hidden=false;result.textContent=accounts.length?accounts.length+" IC Markets demo account(s) found. Select one and tap SYNC ACCOUNT.":"No IC Markets demo accounts were found under this authorization.";}
 }catch(error){if(result){result.hidden=false;result.textContent=error.message;}toast(error.message);}
 finally{button.disabled=false;button.textContent="FIND DEMO ACCOUNTS";}
}
async function selectCTraderDemoAccount(){
 const select=$("ctrader-account-select"),button=$("ctrader-select-account"),result=$("ctrader-result");
 if(!select?.value){toast("Choose an IC Markets demo account first");return;}
 button.disabled=true;button.textContent="SYNCING…";
 try{
  const response=await fetch("/api/connections/ctrader/select",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:select.value})});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Demo account sync failed");
  renderCTraderSnapshot(data);
  $("ctrader-state").textContent="DEMO ACCOUNT SYNCED";
  $("ctrader-note").textContent="IC Markets demo account is connected. Balance and open positions are read from cTrader. Order execution is still disabled.";
  if(result){result.hidden=false;result.textContent="Demo account synchronized successfully.";}
  toast("IC Markets demo account synchronized");
  await loadChart();
 }catch(error){if(result){result.hidden=false;result.textContent=error.message;}toast(error.message);}
 finally{button.disabled=false;button.textContent="SYNC ACCOUNT";}
}
async function refreshCTraderSnapshot(){
 try{
  const response=await fetch("/api/connections/ctrader/snapshot");
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"Account refresh failed");
  renderCTraderSnapshot(data);
 }catch(error){toast(error.message);}
}
$("ctrader-demo-order-form")?.addEventListener("submit",submitCTraderDemoOrder);
$("ctrader-risk-save")?.addEventListener("click",saveCTraderRiskSettings);
$("ctrader-emergency-stop")?.addEventListener("click",toggleCTraderEmergencyStop);
$("ctrader-demo-auth-toggle")?.addEventListener("click",toggleCTraderCustomerAuthorization);
$("ctrader-account-snapshot")?.addEventListener("click",handleCTraderPositionAction);
$("ctrader-discover")?.addEventListener("click",discoverCTraderAccounts);
$("ctrader-select-account")?.addEventListener("click",selectCTraderDemoAccount);
$("ctrader-connect")?.addEventListener("click",async()=>{
 if(!signed){nav("account");toast("Sign in to connect your cTrader account");return;}
 const button=$("ctrader-connect"),result=$("ctrader-result");
 button.disabled=true;button.textContent="PREPARING SECURE CONNECTION…";
 try{
  const response=await fetch("/api/connections/ctrader/start",{method:"POST",headers:{"Content-Type":"application/json"}});
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||"cTrader connection is not ready");
  window.location.assign(data.authorization_url);
 }catch(error){
  result.hidden=false;result.textContent=error.message;toast(error.message);
  button.disabled=false;button.textContent="CONNECT IC MARKETS CTRADER";
 }
});
$("ctrader-refresh")?.addEventListener("click",async()=>{await refreshCTraderStatus();if($("ctrader-account-snapshot")&&!$("ctrader-account-snapshot").hidden)await refreshCTraderSnapshot();});
$("ctrader-disconnect")?.addEventListener("click",async()=>{
 if(!window.confirm("Disconnect your cTrader authorization from QUANTUM AI?"))return;
 try{
  const response=await fetch("/api/connections/ctrader",{method:"DELETE"});
  const data=await response.json();if(!response.ok)throw Error(data.detail||"Disconnect failed");
  $("ctrader-state").textContent="DISCONNECTED";$("ctrader-note").textContent="Your cTrader authorization has been removed from QUANTUM AI.";$("ctrader-account-sync").hidden=true;$("ctrader-account-snapshot").hidden=true;
  $("ctrader-disconnect").hidden=true;$("ctrader-connect").disabled=false;$("ctrader-connect").textContent="CONNECT IC MARKETS CTRADER";
  toast(data.deleted?"cTrader disconnected":"No cTrader authorization was saved");
 }catch(error){toast(error.message);}
});
refreshCTraderStatus();
const ctraderReturn=new URLSearchParams(window.location.search).get("ctrader");
if(ctraderReturn==="authorized"){toast("cTrader authorization received. Account sync is the next step.");}
if(ctraderReturn==="error"){toast("cTrader authorization was not completed. Please try again.");}
if(ctraderReturn){const cleanUrl=window.location.pathname+window.location.hash;window.history.replaceState({},document.title,cleanUrl);}



})();