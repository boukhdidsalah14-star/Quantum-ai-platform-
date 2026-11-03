if (window.Telegram && window.Telegram.WebApp) {
  const tg = window.Telegram.WebApp;
  tg.ready();
  tg.expand();
  try {
    const theme = tg.themeParams || {};
    if (theme.bg_color) document.documentElement.style.setProperty("--tg-bg", theme.bg_color);
    if (theme.text_color) document.documentElement.style.setProperty("--tg-text", theme.text_color);
  } catch (_) {}
}

const symbols=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"];
let selected="BTCUSDT",prices={},candles=[],timeframe="1h",marketSource="binance",selectedCategory="forex",selectedPipSize=null;
function configureSignalTimeframes(){const select=$("signal-timeframe");if(!select)return;const deriv=marketSource.startsWith("deriv_");const allowed=deriv?["1m","5m","15m","30m","1h"]:["1h","4h","1d"];[...select.options].forEach(option=>option.hidden=!allowed.includes(option.value));if(!allowed.includes(select.value))select.value=deriv?"15m":"1h";}
function configureChartTimeframes(){const deriv=marketSource.startsWith("deriv_");const allowed=deriv?["5m","15m","1h","4h","1d"]:["1h","4h","1d"];const buttons=[...document.querySelectorAll(".timeframes [data-tf]")];buttons.forEach(button=>button.hidden=!allowed.includes(button.dataset.tf));if(!allowed.includes(timeframe))timeframe="1h";buttons.forEach(button=>button.classList.toggle("active",button.dataset.tf===timeframe));}
const $=id=>document.getElementById(id);
const money=n=>"$"+Number(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:n>100?2:4});
const pct=n=>(n>=0?"+":"")+Number(n).toFixed(2)+"%";
const escapeHtml=value=>String(value??"").replace(/[&<>"\']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","\'":"&#39;"}[char]));
const derivDecimals=pip=>{const value=Number(pip);return Number.isFinite(value)&&value>0?Math.min(8,Math.max(0,Math.round(-Math.log10(value)))):4};
const formatDerivPrice=(value,pip)=>Number(value).toFixed(derivDecimals(pip));
const formatMarketPrice=item=>marketSource.startsWith("deriv_")?formatDerivPrice(item.price,item.pip_size):money(item.price);

async function loadMarkets(){
  try{
    if(marketSource==="deriv_forex"||marketSource==="deriv_synthetic"||marketSource==="deriv_binary"){
      configureChartTimeframes();
      const category=marketSource==="deriv_forex"?"forex":marketSource==="deriv_synthetic"?"synthetic":"all";
      $("binary-contract-check").hidden=marketSource!=="deriv_binary";
      $("binary-contract-status").textContent="";
      const mr=await fetch("/api/deriv/markets?category="+category);
      if(!mr.ok)throw new Error("Deriv market list unavailable");
      const marketData=await mr.json();
      const sourceMarkets=marketData.markets||[];
      if(!sourceMarkets.length)throw new Error("No active "+category+" markets returned by Deriv");
      if(!sourceMarkets.some(x=>x.symbol===selected))selected=sourceMarkets[0].symbol;
      const granularity={"5m":300,"15m":900,"1h":3600,"4h":14400,"1d":86400}[timeframe]||3600;
      const cr=await fetch("/api/deriv/candles/"+encodeURIComponent(selected)+"?granularity="+granularity+"&count=72");
      if(!cr.ok)throw new Error("Deriv candles unavailable");
      const candleData=await cr.json();
      candles=candleData.candles.map(x=>({o:x.open,h:x.high,l:x.low,c:x.close,v:0}));
      const last=candles[candles.length-1];
      const list=sourceMarkets.map(x=>({symbol:x.symbol,name:x.name,pip_size:x.pip_size,price:x.price??(x.symbol===selected&&last?last.c:null),change_percent:null}));
      renderMarkets(list);
      renderChart();
      $("feed-status").textContent="DERIV PUBLIC · "+category.toUpperCase();
      $("feed-status").style.color="var(--green)";
      const selectedMarket=sourceMarkets.find(x=>x.symbol===selected);
      selectedCategory=selectedMarket?.market||"forex";
      selectedPipSize=selectedMarket?.pip_size||null;
      $("signal-panel").hidden=false;
      $("quote-preview").hidden=false;
      configureSignalTimeframes();
      $("pair-title").innerHTML=(selectedMarket?.name||selected)+" <span class='live-tag'>DERIV</span>";
      $("price").textContent=selectedMarket?.price!==null&&selectedMarket?.price!==undefined?formatDerivPrice(selectedMarket.price,selectedPipSize):last?formatDerivPrice(last.c,selectedPipSize):"—";
      $("change").textContent=selectedMarket?.is_open===false?"MARKET CLOSED":selectedMarket?.price!==null&&selectedMarket?.price!==undefined?"LIVE TICK":"LAST CANDLE";
      $("change").className="positive";
      return;
    }
    $("binary-contract-check").hidden=true;
    $("binary-contract-status").textContent="";
    $("signal-panel").hidden=false;
    $("quote-preview").hidden=true;
    selectedPipSize=null;
    configureSignalTimeframes();
    const sourceOrder=marketSource==="mexc"?["mexc","binance"]:["binance","mexc"];
    let loaded=false,lastError=null;
    for(const source of sourceOrder){
      try{
        const marketPath=source==="mexc"?"/api/mexc/markets":"/api/markets";
        const candlePath=source==="mexc"?"/api/mexc/candles/":"/api/candles/";
        const [mr,cr]=await Promise.all([fetch(marketPath),fetch(candlePath+encodeURIComponent(selected)+"?interval="+encodeURIComponent(timeframe)+"&limit=72")]);
        if(!mr.ok||!cr.ok)throw new Error(source.toUpperCase()+" market feed unavailable");
        const marketData=await mr.json(),candleData=await cr.json();
        if(!symbols.includes(selected))selected=symbols[0];
        const list=(marketData.markets||[]).filter(x=>symbols.includes(x.symbol));
        if(!list.length||!Array.isArray(candleData.candles)||!candleData.candles.length)throw new Error(source.toUpperCase()+" returned no usable market data");
        prices={};
        list.forEach(x=>prices[x.symbol]=x);
        if(!prices[selected])selected=list[0].symbol;
        candles=candleData.candles.map(x=>({o:x.open,h:x.high,l:x.low,c:x.close,v:x.volume}));
        marketSource=source;
        $("market-source").value=source;
        renderMarkets(list);
        renderChart();
        $("feed-status").textContent="LIVE · "+source.toUpperCase()+" PUBLIC DATA";
        $("feed-status").style.color="var(--green)";
        $("pair-title").innerHTML=selected.replace("USDT"," / USDT")+" <span class='live-tag'>LIVE</span>";
        const p=prices[selected];
        if(p){$("price").textContent=money(p.price);$("change").textContent=pct(p.change_percent);$("change").className=+p.change_percent>=0?"positive":"negative"}
        loaded=true;
        break;
      }catch(error){lastError=error}
    }
    if(!loaded)throw lastError||new Error("All public crypto market feeds are unavailable");
  }catch(e){
    $("feed-status").textContent="FEED UNAVAILABLE";$("feed-status").style.color="var(--red)";
    if(!$("ticker").dataset.failed){$("ticker").innerHTML="<div class='ticker-item'>Public market data is temporarily unavailable.</div>";$("ticker").dataset.failed="1"}
  }
}
function renderMarkets(list){
  $("watchlist").innerHTML=list.map(x=>"<div class='asset-row' data-symbol='"+x.symbol+"'><div><span class='asset-name'>"+(x.name||x.symbol.replace("USDT",""))+"</span><span class='asset-symbol'>"+(x.name?" · "+x.symbol:" / USDT")+"</span></div><span class='asset-price'>"+(x.price!==null&&x.price!==undefined&&Number.isFinite(Number(x.price))?formatMarketPrice(x):"—")+"</span><span class='asset-change "+(x.change_percent===null?"":"")+(x.change_percent!==null&&x.change_percent!==undefined?(+x.change_percent>=0?"positive":"negative"):"")+"'>"+(x.change_percent===null||x.change_percent===undefined?"MARKET":pct(x.change_percent))+"</span></div>").join("");
  $("ticker").innerHTML=list.map(x=>"<div class='ticker-item'><b>"+(x.name||x.symbol.replace("USDT","/USDT"))+"</b>"+(x.price!==null&&x.price!==undefined&&Number.isFinite(Number(x.price))?formatMarketPrice(x):"—")+(x.change_percent!==null&&x.change_percent!==undefined?"<span class='"+(+x.change_percent>=0?"positive":"negative")+"'>"+pct(x.change_percent)+"</span>":"")+"</div>").join("");
  $("ticker").dataset.failed="";
  $("watchlist").querySelectorAll(".asset-row").forEach(el=>el.addEventListener("click",()=>{selected=el.dataset.symbol;loadMarkets()}));
}
function renderChart(){
  const c=$("chart"),ctx=c.getContext("2d"),w=c.clientWidth,h=c.clientHeight,dpr=window.devicePixelRatio||1;
  c.width=w*dpr;c.height=h*dpr;ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);if(!candles.length)return;
  const pad={l:8,r:58,t:12,b:20},cw=w-pad.l-pad.r,ch=h-pad.t-pad.b,lo=Math.min(...candles.map(x=>x.l)),hi=Math.max(...candles.map(x=>x.h)),range=hi-lo||1,y=v=>pad.t+(hi-v)/range*ch;
  ctx.font="9px monospace";ctx.strokeStyle="#1b2b22";ctx.fillStyle="#718077";ctx.lineWidth=1;
  const chartDecimals=selectedPipSize?derivDecimals(selectedPipSize):(hi>100?0:4);for(let i=0;i<=4;i++){const yy=pad.t+ch*i/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillText((hi-range*i/4).toFixed(chartDecimals),w-pad.r+7,yy+3)}
  const step=cw/candles.length,bw=Math.max(2,step*.58);
  candles.forEach((d,i)=>{const x=pad.l+i*step+step/2,col=d.c>=d.o?"#8cff3f":"#ff5c68";ctx.strokeStyle=col;ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(x,y(d.h));ctx.lineTo(x,y(d.l));ctx.stroke();ctx.fillRect(x-bw/2,y(Math.max(d.o,d.c)),bw,Math.max(1,Math.abs(y(d.o)-y(d.c))))});
  const last=candles[candles.length-1];ctx.setLineDash([3,4]);ctx.strokeStyle="#8cff3f88";ctx.beginPath();ctx.moveTo(pad.l,y(last.c));ctx.lineTo(w-pad.r,y(last.c));ctx.stroke();ctx.setLineDash([]);ctx.fillStyle="#8cff3f";ctx.fillRect(w-pad.r+3,y(last.c)-8,53,16);ctx.fillStyle="#061006";ctx.fillText(last.c.toFixed(chartDecimals),w-pad.r+6,y(last.c)+3);
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

/* Shared workspace selector: order events switch the central live chart to the traded market. */
window.QUANTUM_SELECT_MARKET = async function (detail) {
  if (!detail || !detail.symbol) return;
  const raw = String(detail.symbol).trim().toUpperCase();
  const platform = String(detail.platform || "").toLowerCase();
  if (platform === "crypto" || /USDT$/.test(raw)) {
    marketSource = "binance";
    selected = raw;
    if (!symbols.includes(selected)) {
      $("feed-status").textContent = "UNSUPPORTED CRYPTO PAIR";
      return;
    }
  } else {
    marketSource = platform === "binary" || platform === "forex" ? "deriv_forex" : marketSource;
    selected = raw.startsWith("FRX") ? raw : "frx" + raw.replace("/", "");
  }
  $("market-source").value = marketSource;
  if (detail.timeframe && ["5m","15m","1h","4h","1d"].includes(detail.timeframe)) timeframe = detail.timeframe;
  configureChartTimeframes();
  await loadMarkets();
  document.querySelectorAll(".timeframes [data-tf]").forEach(button => button.classList.toggle("active", button.dataset.tf === timeframe));
  $("markets").scrollIntoView({behavior:"smooth",block:"start"});
};
window.addEventListener("quantum:trade", event => {
  window.QUANTUM_SELECT_MARKET(event.detail).catch(() => {});
});



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
      $("deriv-capability-tag").textContent=deriv.demo_status_configured?"DEMO · UNVERIFIED":"PUBLIC DATA · DEMO SETUP";
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
    const risk=body.risk||{};
    const riskSummary=$("olymp-risk-summary");
    if(risk.configured){
      $("olymp-account-balance").value=Number(risk.account_balance).toFixed(2);
      riskSummary.textContent="ACCOUNT $"+Number(risk.account_balance).toFixed(2)+" · DAILY LOSS LIMIT 10% = $"+Number(risk.daily_loss_limit).toFixed(2)+" · LOSS TODAY $"+Number(risk.daily_loss).toFixed(2)+" · REMAINING $"+Number(risk.remaining_loss_allowance).toFixed(2)+(risk.trading_paused?" · TRADING PAUSED":"");
      $("olymp-paper-submit").disabled=Boolean(risk.trading_paused);
    }else{
      riskSummary.textContent="Set your paper balance to calculate your 10% daily loss limit. Trading is locked until configured."; $("olymp-paper-submit").disabled=true;
    }
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
  refreshDerivConnection();
  refreshDerivTrades();
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
// Customer-owned Deriv credentials: verify against the user's virtual account before encrypted storage.
async function refreshDerivConnection(){
  const status=$("deriv-customer-status"),remove=$("deriv-customer-remove");
  if(!status)return;
  try{
    const response=await fetch("/api/connections/deriv/demo");
    if(response.status===401){status.textContent="Sign in to manage your Deriv demo connection.";remove.hidden=true;return}
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Connection status unavailable");
    status.textContent=body.connected?"SAVED DEMO CREDENTIALS · Last updated "+new Date(body.updated_at*1000).toLocaleString()+". Verify again before trading features are enabled.":"No Deriv demo account connected.";
    remove.hidden=!body.connected;
  }catch(error){status.textContent=error.message||"Could not load Deriv connection status."}
}
async function refreshDerivTrades(){
  const gate=$("deriv-trade-gate"),submit=$("deriv-trade-submit"),list=$("deriv-trades-list"),risk=$("deriv-risk-status");
  if(!gate||!submit||!list)return;
  try{
    const response=await fetch("/api/deriv/demo/trades");
    const body=await response.json();
    if(response.status===401){gate.textContent="Sign in to use your own Deriv demo account.";submit.disabled=true;return}
    if(!response.ok){gate.textContent=body.detail||"Demo trading is locked.";submit.disabled=true;return}
    const enabled=Boolean(body.execution_enabled);
    submit.disabled=!enabled;
    gate.textContent=enabled?"DEMO ENGINE READY · VRTC ACCOUNTS ONLY · REAL TRADING DISABLED":"Demo history is available, but the demo execution switch is still disabled.";
    if(body.risk){
      const r=body.risk;
      risk.textContent="RISK · Daily net loss "+money(r.daily_net_loss)+" / "+money(r.daily_loss_limit)+" · Consecutive losses "+r.consecutive_losses+" / "+r.max_consecutive_losses+" · Open contracts "+r.open_contracts+" / "+r.max_open_contracts+(r.trading_paused?" · PAUSED: "+r.pause_reasons.join(", "):"");
    }
    list.innerHTML=body.trades.length?body.trades.map(t=>"<article class='deriv-trade-row'><div><strong>"+String(t.symbol)+" · "+String(t.contract_type)+" · "+String(t.status).toUpperCase()+"</strong><small>Stake "+money(t.stake)+" · "+t.duration_minutes+"m · "+(t.contract_id?"Contract "+String(t.contract_id):"Awaiting confirmation")+(t.profit!==null&&t.profit!==undefined?" · P/L "+money(t.profit):"")+(t.error_message?" · "+escapeHtml(t.error_message):"")+"</small></div><span class='locked'>DEMO</span></article>").join(""):"<p class='disclaimer'>No Deriv demo contracts yet.</p>";
  }catch(error){gate.textContent=error.message||"Demo trade status unavailable.";submit.disabled=true}
}
const derivTradeForm=$("deriv-trade-form");
derivTradeForm?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("deriv-trade-submit"),gate=$("deriv-trade-gate");
  button.disabled=true;button.textContent="REQUESTING DERIV PROPOSAL…";
  gate.textContent="Checking risk limits, market availability and your saved VRTC account…";
  try{
    const key=crypto.randomUUID?crypto.randomUUID():String(Date.now())+"-"+Math.random();
    const response=await fetch("/api/deriv/demo/trades",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":key},body:JSON.stringify({symbol:$("deriv-trade-symbol").value,contract_type:$("deriv-trade-direction").value,stake:Number($("deriv-trade-stake").value),duration_minutes:Number($("deriv-trade-duration").value)})});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Deriv demo order failed");
    gate.textContent=(body.duplicate?"DUPLICATE REQUEST BLOCKED · ":"DEMO CONTRACT OPEN · ")+body.trade.symbol+" "+body.trade.contract_type+" · "+body.trade.status.toUpperCase()+". "+body.note;
    await refreshDerivTrades();
  }catch(error){gate.textContent=error.message||"Demo order failed.";await refreshDerivTrades()}
  finally{button.textContent="OPEN DEMO CONTRACT";await refreshDerivTrades()}
});

$("deriv-customer-form")?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("deriv-customer-submit"),status=$("deriv-customer-status");
  button.disabled=true;button.textContent="VERIFYING ACCOUNT…";
  status.textContent="Checking the VRTC demo account with a read-only balance request…";
  try{
    const response=await fetch("/api/connections/deriv/demo/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_id:$("deriv-customer-id").value.trim(),token:$("deriv-customer-token").value})});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Deriv demo verification failed");
    $("deriv-customer-token").value="";
    $("deriv-customer-id").value="";
    status.textContent=body.credential_saved?"DEMO VERIFIED + ENCRYPTED · "+body.account_id+" · Balance "+Number(body.balance.amount).toFixed(2)+" "+body.balance.currency+". Read-only; no trade placed.":"DEMO ACCOUNT VERIFIED · "+body.account_id+" · Balance "+Number(body.balance.amount).toFixed(2)+" "+body.balance.currency+". Credentials were NOT saved because durable encrypted storage is not configured. No trade placed.";
    if(body.credential_saved){await refreshDerivConnection();await refreshDerivTrades()}
  }catch(error){status.textContent=error.message||"Deriv demo verification failed."}
  finally{button.disabled=false;button.textContent="VERIFY + SAVE DEMO"}
});
$("deriv-customer-remove")?.addEventListener("click",async()=>{
  const button=$("deriv-customer-remove"),status=$("deriv-customer-status");
  button.disabled=true;
  try{
    const response=await fetch("/api/connections/deriv/demo",{method:"DELETE"});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Could not remove the saved connection");
    status.textContent="Saved Deriv demo connection removed.";
    button.hidden=true;
  }catch(error){status.textContent=error.message||"Could not remove the connection."}
  finally{button.disabled=false}
});

setInterval(()=>{if(!$("account-profile")?.hidden)refreshDerivTrades()},15000);

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


async function refreshOlympPaperTrades(){
  const list=$("olymp-paper-trades"),message=$("olymp-paper-message");
  if(!list||!message)return;
  try{
    const response=await fetch("/api/olymp-trade/paper/trades");
    if(response.status===401){message.textContent="Sign in to save your private Olymp Trade paper history.";list.innerHTML="";$("olymp-paper-submit").disabled=true;$("olymp-risk-save").disabled=true;return}
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Could not load Olymp Trade paper history");
    message.textContent="PAPER MODE · Choose your trade amount · 10% daily loss cap · 3 open positions · no broker orders.";
    list.innerHTML=body.trades.length?body.trades.map(t=>"<article class='paper-trade'><div><strong>"+escapeHtml(t.symbol)+" · "+t.direction+"</strong><small>"+t.status.toUpperCase()+" · $"+Number(t.stake).toFixed(2)+" · "+t.expiry_minutes+"m · Entry "+t.entry_price+(t.exit_price!==null&&t.exit_price!==undefined?" · Exit "+t.exit_price:"")+(t.pnl!==null&&t.pnl!==undefined?" · P/L $"+Number(t.pnl).toFixed(2):"")+"</small></div>"+(t.status==="open"?"<button type='button' data-olymp-settle='"+t.id+"'>SETTLE SIMULATION</button>":"<span class='locked'>"+String(t.result||"SETTLED").toUpperCase()+"</span>")+"</article>").join(""):"<p class='disclaimer'>No Olymp Trade paper positions yet.</p>";
    list.querySelectorAll("[data-olymp-settle]").forEach(button=>button.addEventListener("click",async()=>{
      const exit=prompt("Enter the checked exit reference price from Olymp Trade (paper simulation only):");
      if(exit===null)return;
      const exitPrice=Number(exit);
      if(!Number.isFinite(exitPrice)||exitPrice<=0){message.textContent="Enter a valid positive exit price.";return}
      button.disabled=true;
      try{
        const settled=await fetch("/api/olymp-trade/paper/trades/"+encodeURIComponent(button.dataset.olympSettle)+"/settle",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({exit_price:exitPrice,payout_rate:0.82})});
        const data=await settled.json();
        if(!settled.ok)throw new Error(data.detail||"Could not settle paper position");
        message.textContent="SIMULATION SETTLED · "+String(data.trade.result).toUpperCase()+" · P/L $"+Number(data.trade.pnl).toFixed(2);
        refreshOlympPaperTrades();
      }catch(error){message.textContent=error.message;button.disabled=false}
    }));
  }catch(error){message.textContent=error.message||"Olymp Trade paper history unavailable"}
}
$("olymp-paper-form")?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("olymp-paper-submit"),message=$("olymp-paper-message");
  button.disabled=true;button.textContent="OPENING SIMULATION…";
  try{
    const key=crypto.randomUUID();
    const payload={symbol:$("olymp-symbol").value,direction:$("olymp-direction").value,stake:Number($("olymp-stake").value),expiry_minutes:Number($("olymp-expiry").value),reference_price:Number($("olymp-entry-price").value),price_source:$("olymp-price-source").value};
    const response=await fetch("/api/olymp-trade/paper/trades",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":key},body:JSON.stringify(payload)});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Paper position could not be opened");
    message.textContent="SIMULATED POSITION OPEN · No Olymp Trade order was sent.";
    refreshOlympPaperTrades();
  }catch(error){message.textContent=error.message||"Paper trade failed"}
  finally{button.disabled=false;button.textContent="OPEN SIMULATED POSITION"}
});
$("olymp-analyze")?.addEventListener("click",async()=>{
  const button=$("olymp-analyze"),result=$("olymp-signal-result");
  if(!candles||candles.length<30){result.textContent="Load at least 30 chart candles before analysis.";return}
  button.disabled=true;button.textContent="ANALYZING…";
  try{
    const tf=marketSource.startsWith("deriv_")?($("signal-timeframe").value||"15m"):timeframe;
    const response=await fetch("/api/olymp-trade/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({timeframe:tf,candles:candles.map((c,i)=>({time:i,open:c.o,high:c.h,low:c.l,close:c.c}))})});
    const body=await response.json();
    if(!response.ok)throw new Error(body.detail||"Signal analysis failed");
    result.innerHTML="<strong>"+body.direction+"</strong> · "+body.trend+" · RSI "+body.rsi_14+" · Strength "+body.signal_strength+"<br>"+(body.reasons||[]).map(escapeHtml).join(" · ")+"<br><small>Chart source: "+escapeHtml(marketSource)+". Not an Olymp Trade quote feed; verify prices independently.</small>";
  }catch(error){result.textContent=error.message||"Signal analysis failed"}
  finally{button.disabled=false;button.textContent="ANALYZE CURRENT CHART"}
});
refreshOlympPaperTrades();

$("olymp-risk-form")?.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=$("olymp-risk-save"),summary=$("olymp-risk-summary");
  button.disabled=true;button.textContent="SAVING…";
  try{
    const response=await fetch("/api/olymp-trade/paper/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_balance:Number($("olymp-account-balance").value)})});
    const body=await response.json(); if(!response.ok)throw new Error(body.detail||"Could not save paper balance");
    const r=body.risk; summary.textContent="ACCOUNT $"+Number(r.account_balance).toFixed(2)+" · DAILY LOSS LIMIT 10% = $"+Number(r.daily_loss_limit).toFixed(2)+" · LOSS TODAY $"+Number(r.daily_loss).toFixed(2)+" · REMAINING $"+Number(r.remaining_loss_allowance).toFixed(2);
    await refreshOlympPaperTrades();
  }catch(error){summary.textContent=error.message||"Could not save paper balance"}
  finally{button.disabled=false;button.textContent="SAVE BALANCE + 10% LOSS LIMIT"}
});