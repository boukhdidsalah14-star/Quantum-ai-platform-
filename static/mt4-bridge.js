(()=>{
 const $=id=>document.getElementById(id);
 const badge=$("mt4-connection-badge"),message=$("mt4-connection-message");
 if(!badge||!message)return;
 const money=value=>value===null||value===undefined?"—":Number(value).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
 function setState(connected,text){
  badge.textContent=connected?"CONNECTED":"NOT CONNECTED";
  badge.classList.toggle("positive",connected);
  message.textContent=text;
 }
 async function refresh(){
  try{
   const response=await fetch("/api/mt4/bridge/status",{cache:"no-store"});
   const data=await response.json();
   if(response.status===401){setState(false,"Sign in to connect your JustMarkets MT4 demo account.");return}
   if(!response.ok)throw new Error(data.detail||"Could not load MT4 connection status");
   $("mt4-account-login").value=data.account_login||$("mt4-account-login").value;
   $("mt4-account-server").value=data.account_server||$("mt4-account-server").value;
   $("mt4-balance").textContent=money(data.balance)+(data.currency?" "+data.currency:"");
   $("mt4-equity").textContent=money(data.equity)+(data.currency?" "+data.currency:"");
   $("mt4-position-count").textContent=String((data.positions||[]).length);
   if(data.connected)setState(true,"JustMarkets MT4 demo terminal is syncing. Last heartbeat: "+new Date(Number(data.last_seen_at)*1000).toLocaleTimeString());
   else if(data.registered)setState(false,"Token registered for this demo account. Attach the EA to MT4 desktop and allow WebRequest to the QUANTUM AI domain.");
   else setState(false,"No MT4 terminal is registered. Use a JustMarkets demo account to begin.");
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
