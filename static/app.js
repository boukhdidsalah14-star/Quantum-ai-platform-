const symbols=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"];
let selected="BTCUSDT",prices={},candles=[],timeframe="1h";
const $=id=>document.getElementById(id);
const money=n=>"$"+Number(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:n>100?2:4});
const pct=n=>(n>=0?"+":"")+Number(n).toFixed(2)+"%";

async function loadMarkets(){
  try{
    const [mr,cr]=await Promise.all([fetch("/api/markets"),fetch("/api/candles/"+encodeURIComponent(selected)+"?interval="+encodeURIComponent(timeframe)+"&limit=72")]);
    if(!mr.ok||!cr.ok)throw new Error("Market API unavailable");
    const marketData=await mr.json(),candleData=await cr.json();
    const list=marketData.markets.filter(x=>symbols.includes(x.symbol));
    list.forEach(x=>prices[x.symbol]=x);
    renderMarkets(list);
    candles=candleData.candles.map(x=>({o:x.open,h:x.high,l:x.low,c:x.close,v:x.volume}));
    renderChart();
    $("feed-status").textContent="LIVE · PUBLIC CRYPTO DATA";
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
  $("watchlist").innerHTML=list.map(x=>"<div class='asset-row' data-symbol='"+x.symbol+"'><div><span class='asset-name'>"+x.symbol.replace("USDT","")+"</span><span class='asset-symbol'> / USDT</span></div><span class='asset-price'>"+money(x.price)+"</span><span class='asset-change "+(+x.change_percent>=0?"positive":"negative")+"'>"+pct(x.change_percent)+"</span></div>").join("");
  $("ticker").innerHTML=list.map(x=>"<div class='ticker-item'><b>"+x.symbol.replace("USDT","/USDT")+"</b>"+money(x.price)+"<span class='"+(+x.change_percent>=0?"positive":"negative")+"'>"+pct(x.change_percent)+"</span></div>").join("");
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
document.querySelectorAll(".tf").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".tf").forEach(x=>x.classList.remove("active"));b.classList.add("active");timeframe=b.dataset.tf;loadMarkets()}));
window.addEventListener("resize",renderChart);loadMarkets();setInterval(loadMarkets,15000);


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
