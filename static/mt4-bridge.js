(()=>{
 const $=id=>document.getElementById(id);
 const badge=$("mt4-connection-badge"),message=$("mt4-connection-message");
 if(!badge||!message)return;
 const money=value=>value===null||value===undefined?"—":Number(value).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
 const price=value=>Number(value).toLocaleString("en-US",{maximumFractionDigits:8});
 let snapshot=null, chartBusy=false;
 function setState(connected,text){
  badge.textContent=connected?"CONNECTED":"NOT CONNECTED";
  badge.classList.toggle("positive",connected);
  message.textContent=text;
 }
 function selectedSymbol(){
  return String($("selectedPair")?.textContent||"EUR/USD").replace(/[^A-Z0-9]/gi,"").toUpperCase();
 }
 function renderPositions(rows){
  const body=$("mt4-position-rows");if(!body)return;
  if(!rows?.length){body.innerHTML='<tr><td colspan="7" style="text-align:center;color:var(--muted)">No connected MT4 positions.</td></tr>';return}
  body.replaceChildren();
  rows.forEach(position=>{
   const tr=document.createElement("tr");
   [position.ticket,position.symbol,position.side,Number(position.lots).toFixed(2),price(position.open_price),price(position.current_price),money(position.profit)].forEach(value=>{
    const td=document.createElement("td");td.textContent=String(value);tr.appendChild(td);
   });
   body.appendChild(tr);
  });
 }
 function renderQuotes(quotes){
  const body=$("forexRows");if(!body||!quotes)return;
  const current=selectedSymbol();
  body.replaceChildren();
  Object.entries(quotes).forEach(([symbol,quote])=>{
   const tr=document.createElement("tr");
   const spread=Number(quote.ask)-Number(quote.bid);
   [symbol,price(quote.bid),price(quote.ask),price(spread)].forEach(value=>{const td=document.createElement("td");td.textContent=String(value);tr.appendChild(td)});
   if(symbol===current)tr.style.background="#1b3553";
   tr.addEventListener("click",()=>{
    body.querySelectorAll("tr").forEach(row=>row.style.background="");
    tr.style.background="#1b3553";
    $("selectedPair").textContent=symbol;
    loadBrokerCandles();
   });
   body.appendChild(tr);
  });
 }
 function drawBrokerCandles(rows,positions){
  const canvas=$("forexChart");if(!canvas||!rows?.length)return;
  const w=canvas.clientWidth,h=canvas.clientHeight,dpr=window.devicePixelRatio||1;
  canvas.width=Math.max(1,w*dpr);canvas.height=Math.max(1,h*dpr);
  const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const values=rows.map(c=>({o:+c.open,h:+c.high,l:+c.low,c:+c.close}));
  const levels=values.flatMap(c=>[c.h,c.l]);
  (positions||[]).forEach(p=>{if(p.symbol===selectedSymbol()){levels.push(+p.open_price);if(+p.stop_loss>0)levels.push(+p.stop_loss);if(+p.take_profit>0)levels.push(+p.take_profit)}});
  const lo=Math.min(...levels),hi=Math.max(...levels),span=hi-lo||1,pad=18,step=(w-pad*2)/values.length,bw=Math.max(2,step*.62);
  const y=v=>pad+(hi-v)/span*(h-pad*2);
  ctx.strokeStyle="#233b55";ctx.lineWidth=1;
  for(let i=0;i<5;i++){const yy=pad+(h-pad*2)*i/4;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(w,yy);ctx.stroke()}
  values.forEach((c,i)=>{const x=pad+i*step+step/2,up=c.c>=c.o,color=up?"#18d995":"#ff526d";ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y(c.h));ctx.lineTo(x,y(c.l));ctx.stroke();ctx.fillRect(x-bw/2,Math.min(y(c.o),y(c.c)),bw,Math.max(1,Math.abs(y(c.o)-y(c.c))))});
  (positions||[]).filter(p=>p.symbol===selectedSymbol()).forEach(p=>{
   const markers=[["ENTRY",+p.open_price,"#ffc857"],["SL",+p.stop_loss,"#ff526d"],["TP",+p.take_profit,"#18d995"]];
   markers.forEach(([label,value,color])=>{if(!Number.isFinite(value)||value<=0)return;ctx.setLineDash([5,4]);ctx.strokeStyle=color;ctx.beginPath();ctx.moveTo(0,y(value));ctx.lineTo(w,y(value));ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font="bold 10px Arial";ctx.fillText(label+" "+value.toPrecision(7),8,Math.max(12,y(value)-5))});
  });
 }
 async function loadBrokerCandles(){
  if(chartBusy||!snapshot?.connected)return;
  chartBusy=true;
  try{
   const symbol=selectedSymbol();
   const response=await fetch("/api/mt4/candles/"+encodeURIComponent(symbol)+"?timeframe=15m",{cache:"no-store"});
   const data=await response.json();
   if(!response.ok)throw new Error(data.detail||"Waiting for MT4 broker candles");
   drawBrokerCandles(data.candles,snapshot.positions||[]);
   $("mt4-chart-source").textContent="Chart source: JustMarkets MT4 broker candles · "+symbol+" · 15m";
  }catch(error){
   $("mt4-chart-source").textContent=error.message||"MT4 candles not yet available. The EA uploads candles after it starts.";
  }finally{chartBusy=false}
 }
 async function refresh(){
  try{
   const response=await fetch("/api/mt4/bridge/status",{cache:"no-store"});
   const data=await response.json();
   if(response.status===401){snapshot=null;setState(false,"Sign in to connect your JustMarkets MT4 demo account.");return}
   if(!response.ok)throw new Error(data.detail||"Could not load MT4 connection status");
   snapshot=data;
   $("mt4-account-login").value=data.account_login||$("mt4-account-login").value;
   $("mt4-account-server").value=data.account_server||$("mt4-account-server").value;
   $("mt4-balance").textContent=money(data.balance)+(data.currency?" "+data.currency:"");
   $("mt4-equity").textContent=money(data.equity)+(data.currency?" "+data.currency:"");
   $("mt4-position-count").textContent=String((data.positions||[]).length);
   $("mt4-account-balance-large").textContent=data.connected?money(data.balance)+" "+(data.currency||""):"NOT CONNECTED";
   $("mt4-account-equity-large").textContent=data.connected?"Equity "+money(data.equity)+" "+(data.currency||""):"A verified MT4 demo balance appears here after connection.";
   renderPositions(data.positions||[]);
   if(data.connected){
    setState(true,"JustMarkets MT4 demo terminal is syncing. Last heartbeat: "+new Date(Number(data.last_seen_at)*1000).toLocaleTimeString());
    renderQuotes(data.quotes||{});
    await loadBrokerCandles();
   }else if(data.registered){
    setState(false,"Token registered for this demo account. Attach the EA to MT4 desktop and allow WebRequest to the QUANTUM AI domain.");
   }else{
    setState(false,"No MT4 terminal is registered. Use a JustMarkets demo account to begin.");
   }
  }catch(error){setState(false,error.message||"MT4 status unavailable")}
 }
 $("mt4-refresh")?.addEventListener("click",refresh);
 $("mt4-register")?.addEventListener("click",async()=>{
  const button=$("mt4-register"),login=$("mt4-account-login").value.trim(),server=$("mt4-account-server").value.trim();
  if(!/^\d{5,12}$/.test(login)||!server){setState(false,"Enter the numeric MT4 login and exact server name.");return}
  button.disabled=true;button.textContent="REGISTERING…";
  try{
   const response=await fetch("/api/mt4/bridge/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({account_login:login,account_server:server})});
   const data=await response.json();if(!response.ok)throw new Error(data.detail||"Could not register MT4 bridge");
   $("mt4-token").textContent=data.bridge_token;
   $("mt4-token-panel").hidden=false;
   setState(false,"Token generated. Copy it now, then install the read-only EA in your JustMarkets MT4 demo terminal.");
   await refresh();
  }catch(error){setState(false,error.message||"MT4 registration failed")}
  finally{button.disabled=false;button.textContent="GENERATE READ-ONLY TOKEN"}
 });
 $("mt4-copy-token")?.addEventListener("click",async()=>{
  try{await navigator.clipboard.writeText($("mt4-token").textContent);message.textContent="Bridge token copied. Store it securely."}
  catch{message.textContent="Copy unavailable. Select the token text and copy it manually."}
 });
 $("mt4-token-panel").hidden=true;
 refresh();
 setInterval(refresh,15000);
})();
