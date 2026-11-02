const symbols=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"];
let selected="BTCUSDT",prices={},candles=[],timeframe="1h",marketSource="binance",selectedCategory="forex";
function configureSignalTimeframes(){const select=$("signal-timeframe");if(!select)return;const deriv=marketSource.startsWith("deriv_");const allowed=deriv?["1m","5m","15m","30m","1h"]:["1h","4h","1d"];[...select.options].forEach(option=>option.hidden=!allowed.includes(option.value));if(!allowed.includes(select.value))select.value=deriv?"15m":"1h";}
const $=id=>document.getElementById(id);
const money=n=>"$"+Number(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:n>100?2:4});
const pct=n=>(n>=0?"+":"")+Number(n).toFixed(2)+"%";

async function loadMarkets(){
  try{
    if(marketSource==="deriv_forex"||marketSource==="deriv_synthetic"||marketSource==="deriv_binary"){
      const category=marketSource==="deriv_forex"?"forex":marketSource==="deriv_synthetic"?"synthetic":"all";
      $("binary-contract-check").hidden=marketSource!=="deriv_binary";
      $("binary-contract-status").textContent="";
      const mr=await fetch("/api/deriv/markets?category="+category);
      if(!mr.ok)throw new Error("Deriv market list unavailable");
      const marketData=await mr.json();
      const sourceMarkets=marketData.markets||[];
      if(!sourceMarkets.length)throw new Error("No active "+category+" markets returned by Deriv");
      if(!sourceMarkets.some(x=>x.symbol===selected))selected=sourceMarkets[0].symbol;
      const granularity={"15m":900,"1h":3600,"4h":14400,"1d":86400}[timeframe]||3600;
      const cr=await fetch("/api/deriv/candles/"+encodeURIComponent(selected)+"?granularity="+granularity+"&count=72");
      if(!cr.ok)throw new Error("Deriv candles unavailable");
      const candleData=await cr.json();
      candles=candleData.candles.map(x=>({o:x.open,h:x.high,l:x.low,c:x.close,v:0}));
      const last=candles[candles.length-1];
      const list=sourceMarkets.map(x=>({symbol:x.symbol,name:x.name,price:x.symbol===selected&&last?last.c:null,change_percent:null}));
      renderMarkets(list);
      renderChart();
      $("feed-status").textContent="DERIV PUBLIC · "+category.toUpperCase();
      $("feed-status").style.color="var(--green)";
      const selectedMarket=sourceMarkets.find(x=>x.symbol===selected);
      selectedCategory=selectedMarket?.market||"forex";
      $("signal-panel").hidden=false;
      $("quote-preview").hidden=false;
      configureSignalTimeframes();
      $("pair-title").innerHTML=(selectedMarket?.name||selected)+" <span class='live-tag'>DERIV</span>";
      $("price").textContent=last?money(last.c):"—";
      $("change").textContent=selectedMarket?.is_open===false?"MARKET CLOSED":"LAST CANDLE";
      $("change").className="positive";
      return;
    }
    $("binary-contract-check").hidden=true;
    $("binary-contract-status").textContent="";
    $("signal-panel").hidden=false;
    $("quote-preview").hidden=true;
    configureSignalTimeframes();
    const marketPath=marketSource==="mexc"?"/api/mexc/markets":"/api/markets";
    const candlePath=marketSource==="mexc"?"/api/mexc/candles/":"/api/candles/";
    const [mr,cr]=await Promise.all([fetch(marketPath),fetch(candlePath+encodeURIComponent(selected)+"?interval="+encodeURIComponent(timeframe)+"&limit=72")]);
    if(!mr.ok||!cr.ok)throw new Error("Market API unavailable");
    const marketData=await mr.json(),candleData=await cr.json();
    if(!symbols.includes(selected))selected=symbols[0];
    const list=marketData.markets.filter(x=>symbols.includes(x.symbol));
    list.forEach(x=>prices[x.symbol]=x);
    renderMarkets(list);
    candles=candleData.candles.map(x=>({o:x.open,h:x.high,l:x.low,c:x.close,v:x.volume}));
    renderChart();
    $("feed-status").textContent="LIVE · "+marketSource.toUpperCase()+" PUBLIC DATA";
    $("feed-status").style.color="var(--green)";
    $("pair-title").innerHTML=selected.replace("USDT"," / USDT")+" <span class='live-tag'>LIVE</span>";
    const p=prices[selected];
    if(p){$("price").textContent=money(p.price);$("change").textContent=pct(p.change_percent);$("change").className=+p.change_percent>=0?"positive":"negative"}
  }catch(e){
    $("feed-status").textContent="FEED UNAVAILABLE";$("feed-status").style.color="var(--red)";
    if(!$("ticker").dataset.failed){$("ticker").innerHTML="<div class='ticker-item'>Public market data is temporarily unavailable.</div>";$("ticker").dataset.failed="1"}
  }
}
function renderMarkets(list){
  $("watchlist").innerHTML=list.map(x=>"<div class='asset-row' data-symbol='"+x.symbol+"'><div><span class='asset-name'>"+(x.name||x.symbol.replace("USDT",""))+"</span><span class='asset-symbol'>"+(x.name?" · "+x.symbol:" / USDT")+"</span></div><span class='asset-price'>"+(x.price!==null&&x.price!==undefined&&Number.isFinite(Number(x.price))?money(x.price):"—")+"</span><span class='asset-change "+(x.change_percent===null?"":"")+(x.change_percent!==null&&x.change_percent!==undefined?(+x.change_percent>=0?"positive":"negative"):"")+"'>"+(x.change_percent===null||x.change_percent===undefined?"MARKET":pct(x.change_percent))+"</span></div>").join("");
  $("ticker").innerHTML=list.map(x=>"<div class='ticker-item'><b>"+(x.name||x.symbol.replace("USDT","/USDT"))+"</b>"+(x.price!==null&&x.price!==undefined&&Number.isFinite(Number(x.price))?money(x.price):"—")+(x.change_percent!==null&&x.change_percent!==undefined?"<span class='"+(+x.change_percent>=0?"positive":"negative")+"'>"+pct(x.change_percent)+"</span>":"")+"</div>").join("");
  $("ticker").dataset.failed="";
  $("watchlist").querySelectorAll(".asset-row").forEach(el=>el.addEventListener("click",()=>{selected=el.dataset.symbol;loadMarkets()}));
}
function renderChart(){
  const c=$("chart"),ctx=c.getContext("2d"),w=c.clientWidth,h=c.clientHeight,dpr=window.devicePixelRatio||1;
  c.width=w*dpr;c.height=h*dpr;ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);if(!candles.length)return;
  const pad={l:8,r:58,t:12,b:20},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b,lo=Math.min(...candles.map(x=>x.l)),hi=Math.max(...candles.map(x=>x.h)),range=hi-lo||1,y=v=>pad.t+(hi-v)/range*ch;
  ctx.font="9px monospace";ctx.strokeStyle="#1b2b22";ctx.fillStyle="#718077";ctx.lineWidth=1;
  for(let i=0;i<=4;i++){const yy=pad.t+ch*i/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillText((hi-range*i/4).toFixed(hi>100?0:4),w-pad.r+7,yy+3)}
  const step=cw/candles.length,bw=Math.max(2,step*.58);
  candles.forEach((d,i)=>{const x=pad.l+i*step+step/2,col=d.c>=d.o?"#8cff3f":"#ff5c68";ctx.strokeStyle=col;ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(x,y(d.h));ctx.lineTo(x,y(d.l));ctx.stroke();ctx.fillRect(x-bw/2,y(Math.max(d.o,d.c)),bw,Math.max(1,Math.abs(y(d.o)-y(d.c))))});
  const last=candles[candles.length-1];ctx.setLineDash([3,4]);ctx.strokeStyle="#8cff3f88";ctx.beginPath();ctx.moveTo(pad.l,y(last.c));ctx.lineTo(w-pad.r,y(last.c));ctx.stroke();ctx.setLineDash([]);ctx.fillStyle="#8cff3f";ctx.fillRect(w-pad.r+3,y(last.c)-8,53,16);ctx.fillStyle="#061006";ctx.fillText(last.c.toFixed(hi>100?1:5),w-pad.r+6,y(last.c)+3);
}
document.querySelectorAll(".timeframes [data-tf]").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".timeframes [data-tf]").forEach(x=>x.classList.remove("active"));b.classList.add("active");timeframe=b.dataset.tf;loadMarkets()}));
$("run-backtest")?.addEventListener("click",async()=>{
  const button=$("run-backtest"),result=$("backtest-result");
  button.disabled=true;button.textContent="TESTING…";
  result.textContent="Evaluating historical candles without placing trades…";
  try{
    const signalTimeframe=$("signal-timeframe").value;
    const url=marketSource.startsWith("deriv_")?"/api/backtest/deriv/"+encodeURIComponent(selected)+"?category="+encodeURIComponent(selectedCategory)+"&timeframe="+encodeURIComponent(signalTimeframe)+"&lookahead_candles=1":"/api/backtest/crypto/"+encodeURIComponent(selected)+"?source="+encodeURIComponent(marketSource)+"&timeframe="+encodeURIComponent(signalTimeframe)+"&lookahead_candles=1";
    const response=await fetch(url);
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Backtest unavailable");
    const accuracy=body.directional_accuracy_percent===null?"Not enough directional signals":body.directional_accuracy_percent+"% directional accuracy";
    result.textContent=accuracy+" · "+body.wins+" wins · "+body.losses+" losses · "+body.waits+" WAITs · "+body.candles_tested+" candles. Historical test only; not a profit forecast.";
  }catch(error){result.textContent=error.message||"Backtest failed"}
  finally{button.disabled=false;button.textContent="TEST LAST 200 CANDLES"}
});
$("get-demo-quote")?.addEventListener("click",async()=>{
  const button=$("get-demo-quote"),result=$("quote-result");
  button.disabled=true;button.textContent="REQUESTING…";
  result.textContent="Requesting a public contract price. No trade will be placed.";
  try{
    const params=new URLSearchParams({
      contract_type:$("quote-direction").value,
      amount:$("quote-stake").value,
      duration:$("quote-duration").value,
      currency:"USD"
    });
    const response=await fetch("/api/deriv/proposal/"+encodeURIComponent(selected)+"?"+params.toString());
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Quote unavailable for this market");
    result.textContent=body.contract_type+" · "+body.symbol+" · Stake "+Number(body.stake).toFixed(2)+" "+body.currency+" · Potential payout "+Number(body.payout).toFixed(2)+" "+body.currency+". "+(body.longcode||"Price quote only; no order sent.");
  }catch(error){result.textContent=error.message||"Quote request failed"}
  finally{button.disabled=false;button.textContent="GET PRICE QUOTE"}
});
$("analyze-signal")?.addEventListener("click",async()=>{
  const button=$("analyze-signal"),result=$("signal-result");
  button.disabled=true;button.textContent="ANALYZING…";
  result.textContent="Reviewing completed candles…";
  try{
    const signalTimeframe=$("signal-timeframe").value;
    const url=marketSource.startsWith("deriv_")?"/api/signals/deriv/"+encodeURIComponent(selected)+"?category="+encodeURIComponent(selectedCategory)+"&timeframe="+encodeURIComponent(signalTimeframe):"/api/signals/crypto/"+encodeURIComponent(selected)+"?source="+encodeURIComponent(marketSource)+"&timeframe="+encodeURIComponent(signalTimeframe);
    const response=await fetch(url);
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Signal analysis unavailable");
    const direction=body.direction||"WAIT";
    const tone=direction==="PUT"?"signal-put":"";
    const reasons=(body.reasons||[]).map(reason=>"<li>"+String(reason).replace(/[&<>"]/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[char]))+"</li>").join("");
    result.innerHTML="<strong class='"+tone+"'>"+direction+"</strong> · "+body.symbol+" · "+body.timeframe+"<br>Trend: "+body.trend+" · RSI(14): "+body.rsi_14+" · Signal strength: "+body.signal_strength+"<br>Suggested expiry reference: "+(body.suggested_expiry_minutes||"—")+" min<ul class='signal-reasons'>"+reasons+"</ul>";
  }catch(error){result.textContent=error.message||"Signal analysis failed"}
  finally{button.disabled=false;button.textContent="ANALYZE MARKET"}
});
$("binary-contract-check")?.addEventListener("click",async()=>{
  const button=$("binary-contract-check"),status=$("binary-contract-status");
  button.disabled=true;button.textContent="CHECKING…";
  try{
    const response=await fetch("/api/deriv/contracts/"+encodeURIComponent(selected));
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Contract metadata unavailable");
    const names=(body.contracts||[]).map(x=>x.contract_display||x.contract_type).filter(Boolean);
    status.textContent=names.length?"AVAILABLE: "+names.slice(0,6).join(" · "):"No binary contracts listed for this symbol.";
  }catch(error){status.textContent=error.message||"Contract lookup failed."}
  finally{button.disabled=false;button.textContent="CHECK CONTRACTS"}
});
window.addEventListener("resize",renderChart);
$("market-source")?.addEventListener("change",event=>{marketSource=event.target.value;if(!marketSource.startsWith("deriv_")&&!symbols.includes(selected))selected=symbols[0];loadMarkets()});
loadMarkets();setInterval(loadMarkets,15000);


const derivButton=$("deriv-check");
if(derivButton){
  derivButton.addEventListener("click",async()=>{
    const result=$("deriv-status-result");
    derivButton.disabled=true;
    derivButton.textContent="CHECKING…";
    result.textContent="Checking the configured Deriv demo account (read-only)…";
    try{
      const adminKey=$("deriv-admin-key").value.trim();
      if(!adminKey)throw new Error("Enter the admin status key first.");
      const response=await fetch("/api/deriv/demo/status",{headers:{"X-Admin-Key":adminKey}});
      const body=await response.json();
      if(!response.ok)throw new Error(body.detail||"Demo connection unavailable");
      result.textContent="DEMO CONNECTED · "+body.account_id+" · Balance: "+body.balance.amount+" "+body.balance.currency+" · "+body.active_symbols_count+" active symbols. Read-only; order execution remains disabled.";
    }catch(error){
      result.textContent=error.message||"Deriv demo connection could not be verified.";
    }finally{
      derivButton.disabled=false;
      derivButton.textContent="CHECK DERIV DEMO";
    }
  });
}


// Broker capability display is driven by the backend registry, never guessed in the browser.
async function loadBrokerCapabilities(){
  try{
    const response=await fetch("/api/brokers");
    if(!response.ok)throw new Error("Broker status unavailable");
    const body=await response.json();
    const deriv=body.brokers.find(item=>item.id==="deriv");
    if(deriv){
      $("deriv-capability").textContent=deriv.note;
      $("deriv-capability-tag").textContent=deriv.status==="demo_status_configured"?"CONFIGURED · NOT VERIFIED":"SETUP REQUIRED";
      $("deriv-capability-tag").className="tag-pending";
    }
  }catch{
    $("deriv-capability").textContent="Status could not be loaded";
  }
}
loadBrokerCapabilities();

// Customer-isolated paper trading; every price is a public quote and every order is simulated.
async function refreshPaperTrades(){
  const list=$("paper-trades-list"),message=$("paper-message");
  if(!list||!message)return;
  try{
    const response=await fetch("/api/paper/trades");
    if(response.status===401){list.innerHTML="";message.textContent="Sign in to save your private paper-trading history.";return}
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Could not load paper trades");
    message.textContent="PAPER MODE · Max $500 notional per trade · Up to 5 open trades.";
    list.innerHTML=body.trades.length?body.trades.map(t=>"<article class='paper-trade'><div><strong>"+t.symbol+" · "+t.side.toUpperCase()+"</strong><small>"+t.status.toUpperCase()+" · Qty "+Number(t.quantity)+" · Entry "+money(t.entry_price)+(t.exit_price?" · Exit "+money(t.exit_price):"")+(t.realized_pnl!==null&&t.realized_pnl!==undefined?" · Realized "+money(t.realized_pnl):(t.unrealized_pnl!==undefined?" · Unrealized "+money(t.unrealized_pnl):""))+"</small></div>"+(t.status==="open"?"<button type='button' data-close-paper='"+t.id+"'>CLOSE AT MARKET</button>":"<span class='locked'>SETTLED</span>")+"</article>").join(""):"<p class='disclaimer'>No paper trades yet. Open a simulated position above.</p>";
  }catch(error){message.textContent=error.message||"Paper trading unavailable"}
}
const paperForm=$("paper-form");
paperForm?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("paper-submit"),message=$("paper-message");
  button.disabled=true;button.textContent="OPENING SIMULATION…";
  try{
    const response=await fetch("/api/paper/trades",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":(crypto.randomUUID?crypto.randomUUID():String(Date.now())+"-"+Math.random())},body:JSON.stringify({symbol:$("paper-symbol").value,side:$("paper-side").value,quantity:Number($("paper-quantity").value)})});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Paper trade could not be opened");
    message.textContent="SIMULATED POSITION OPEN · "+body.trade.symbol+" at "+money(body.trade.entry_price)+". No broker order was sent.";
    await refreshPaperTrades();
  }catch(error){message.textContent=error.message||"Paper trade failed"}
  finally{button.disabled=false;button.textContent="OPEN PAPER TRADE"}
});
$("paper-trades-list")?.addEventListener("click",async event=>{
  const button=event.target.closest("[data-close-paper]");
  if(!button)return;
  button.disabled=true;button.textContent="CLOSING…";
  try{
    const response=await fetch("/api/paper/trades/"+encodeURIComponent(button.dataset.closePaper)+"/close",{method:"POST"});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Paper trade could not be closed");
    $("paper-message").textContent="PAPER TRADE SETTLED · P/L "+money(body.trade.realized_pnl)+".";
    await refreshPaperTrades();
  }catch(error){$("paper-message").textContent=error.message||"Close failed";button.disabled=false;button.textContent="CLOSE AT MARKET"}
});

// Customer account access: authentication only; no broker credentials are handled here.
const accountPanel=$("account-panel");
const accountToggle=$("account-toggle");
let authMode="login";
let registrationEnabled=false;
function showAuthMessage(message,isError=false){
  const node=$("auth-message");
  node.textContent=message;
  node.classList.toggle("error",isError);
}
function showCustomer(customer){
  $("auth-form").hidden=true;
  $("auth-mode").hidden=true;
  $("account-profile").hidden=false;
  $("account-title").textContent="Your account";
  $("account-email").textContent=customer.email;
  showAuthMessage("Signed in. Paper trading is available; broker order execution remains disabled.");
  refreshPaperTrades();
}
function showSignedOut(){
  $("auth-form").hidden=false;
  $("auth-mode").hidden=!registrationEnabled;
  $("account-profile").hidden=true;
  $("account-title").textContent="Account access";
  if($("paper-trades-list")){$("paper-trades-list").innerHTML="";$("paper-message").textContent="Sign in to save your private paper-trading history.";}
  $("auth-submit").textContent=authMode==="login"?"SIGN IN":"CREATE ACCOUNT";
  $("auth-password").setAttribute("autocomplete",authMode==="login"?"current-password":"new-password");
  $("auth-mode").textContent=authMode==="login"?"Need an account? Create one":"Already registered? Sign in";
}
async function refreshCustomer(){
  try{
    const response=await fetch("/api/auth/me");
    if(response.ok){const body=await response.json();showCustomer(body.customer)}
    else showSignedOut();
  }catch{showSignedOut()}
}
accountToggle?.addEventListener("click",()=>{
  const open=accountPanel.hidden;
  accountPanel.hidden=!open;
  accountToggle.setAttribute("aria-expanded",String(open));
  if(open)refreshCustomer();
});
$("account-close")?.addEventListener("click",()=>{
  accountPanel.hidden=true;
  accountToggle.setAttribute("aria-expanded","false");
});
$("auth-mode")?.addEventListener("click",()=>{
  if(!registrationEnabled)return;
  authMode=authMode==="login"?"register":"login";
  showSignedOut();
  showAuthMessage(authMode==="register"?"Account creation is controlled by the platform.":"Sign in to access your customer workspace.");
});
$("auth-form")?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("auth-submit");
  button.disabled=true;
  button.textContent="PLEASE WAIT…";
  try{
    const endpoint=authMode==="login"?"/api/auth/login":"/api/auth/register";
    const response=await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("auth-email").value.trim(),password:$("auth-password").value})});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Account request failed");
    $("auth-password").value="";
    showCustomer(body.customer);
  }catch(error){showAuthMessage(error.message||"Account request failed",true)}
  finally{button.disabled=false;button.textContent=authMode==="login"?"SIGN IN":"CREATE ACCOUNT"}
});
$("auth-logout")?.addEventListener("click",async()=>{
  try{await fetch("/api/auth/logout",{method:"POST"});authMode="login";showSignedOut();showAuthMessage("You have signed out.")}
  catch{showAuthMessage("Could not sign out. Please retry.",true)}
});

async function loadAuthConfig(){
  try{
    const response=await fetch("/api/auth/config");
    if(!response.ok)throw new Error("Account settings unavailable");
    const body=await response.json();
    registrationEnabled=body.registration_enabled===true;
  }catch{
    registrationEnabled=false;
  }
  if(!registrationEnabled)authMode="login";
  if(!$("auth-form").hidden){
    $("auth-mode").hidden=!registrationEnabled;
    $("auth-submit").textContent="SIGN IN";
    $("auth-password").setAttribute("autocomplete","current-password");
    if(!registrationEnabled)showAuthMessage("New customer registration is currently closed. Sign in if you already have an account.");
  }
}
loadAuthConfig();
