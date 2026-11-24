import http from "node:http";
import { readFile } from "node:fs/promises";
import { createHmac, timingSafeEqual, randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";
import { SESv2Client, SendEmailCommand } from "@aws-sdk/client-sesv2";

const { Pool } = pg;
const __dirname=path.dirname(fileURLToPath(import.meta.url));
const publicDir=path.join(__dirname,"public");
const port=Number(process.env.PORT||3000);
const adminPassword=process.env.ADMIN_PASSWORD||"";
const sessionSecret=process.env.SESSION_SECRET||"";
const databaseUrl=process.env.DATABASE_URL||"";
const pool=databaseUrl?new Pool({connectionString:databaseUrl,ssl:{rejectUnauthorized:false},max:5}):null;
const sesReady=Boolean(process.env.AWS_ACCESS_KEY_ID&&process.env.AWS_SECRET_ACCESS_KEY&&process.env.AWS_REGION&&process.env.MAIL_FROM&&process.env.PUBLIC_APP_URL);
const ses=sesReady?new SESv2Client({region:process.env.AWS_REGION,credentials:{accessKeyId:process.env.AWS_ACCESS_KEY_ID,secretAccessKey:process.env.AWS_SECRET_ACCESS_KEY}}):null;
const ttl=8*60*60;
function sign(v){return createHmac("sha256",sessionSecret).update(v).digest("base64url")}
function token(payload){const p=Buffer.from(JSON.stringify(payload)).toString("base64url");return p+"."+sign(p)}
function validToken(t){if(!t||!sessionSecret)return false;const [p,s]=t.split(".");if(!p||!s)return false;const a=Buffer.from(s),b=Buffer.from(sign(p));if(a.length!==b.length||!timingSafeEqual(a,b))return false;try{return JSON.parse(Buffer.from(p,"base64url").toString()).exp>Date.now()/1000}catch{return false}}
function cookie(req){return Object.fromEntries((req.headers.cookie||"").split(";").map(x=>x.trim()).filter(Boolean).map(x=>{const i=x.indexOf("=");return[x.slice(0,i),decodeURIComponent(x.slice(i+1))]}))}
function auth(req){return validToken(cookie(req).qmail_session)}
function send(res,status,data,headers={}){res.writeHead(status,{"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff",...headers});res.end(JSON.stringify(data))}
async function readBody(req){let s="";for await(const c of req){s+=c;if(s.length>1_000_000)throw Error("Request too large")}return s?JSON.parse(s):{}}
function emailOk(v){return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v||""))}
function escapeHtml(s=""){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function migrate(){if(!pool)return;await pool.query(`
CREATE TABLE IF NOT EXISTS contacts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),email text NOT NULL UNIQUE,name text NOT NULL DEFAULT '',consent boolean NOT NULL DEFAULT false,consent_source text,consent_at timestamptz,unsubscribed_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS campaigns(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),name text NOT NULL,subject text NOT NULL,body text NOT NULL,status text NOT NULL DEFAULT 'draft',created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS campaign_events(id bigserial PRIMARY KEY,campaign_id uuid REFERENCES campaigns(id) ON DELETE CASCADE,contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,event_type text NOT NULL,provider_message_id text,metadata jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS settings(key text PRIMARY KEY,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS suppression_list(email text PRIMARY KEY,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS contacts_consent_idx ON contacts(consent,unsubscribed_at);
CREATE INDEX IF NOT EXISTS campaign_events_campaign_idx ON campaign_events(campaign_id,created_at DESC);
`)}
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,"http://localhost"),p=url.pathname;
 if(p==="/api/health")return send(res,200,{ok:true,app:"QUANTUM AI Mailer",version:"0.2.0",database:Boolean(pool),providerConfigured:sesReady});
 if(p.startsWith("/track/")&&req.method==="GET"){const t=p.slice(7);if(!validToken(t))return send(res,400,{error:"Invalid tracking link"});try{const d=JSON.parse(Buffer.from(t.split(".")[0],"base64url").toString());const target=new URL(d.url);if(!["http:","https:"].includes(target.protocol))return send(res,400,{error:"Invalid destination"});if(pool)await pool.query("INSERT INTO campaign_events(campaign_id,contact_id,event_type,metadata) VALUES($1,$2,'click',$3)",[d.campaignId,d.cid,JSON.stringify({url:d.url})]);res.writeHead(302,{"location":target.toString(),"cache-control":"no-store"});return res.end()}catch{return send(res,400,{error:"Invalid tracking link"})}}
 if(p==="/api/auth/status")return send(res,200,{authenticated:auth(req),passwordConfigured:Boolean(adminPassword&&sessionSecret)});
 if(p==="/api/login"&&req.method==="POST"){if(!adminPassword||!sessionSecret)return send(res,503,{error:"Owner login is not configured"});try{const d=await readBody(req),a=Buffer.from(String(d.password||"")),b=Buffer.from(adminPassword);if(a.length!==b.length||!timingSafeEqual(a,b))return send(res,401,{error:"Incorrect password"});return send(res,200,{ok:true},{"set-cookie":`qmail_session=${encodeURIComponent(token({exp:Math.floor(Date.now()/1000)+ttl}))}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${ttl}${process.env.NODE_ENV==="production"?"; Secure":""}`})}catch{return send(res,400,{error:"Invalid request"})}}
 if(p==="/api/logout"&&req.method==="POST")return send(res,200,{ok:true},{"set-cookie":"qmail_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"});
 if(p==="/unsubscribe"&&req.method==="GET"){const t=url.searchParams.get("t");if(!validToken(t))return send(res,400,{error:"Invalid or expired unsubscribe link"});const d=JSON.parse(Buffer.from(t.split(".")[0],"base64url").toString());await pool.query("UPDATE contacts SET unsubscribed_at=now(),updated_at=now() WHERE id=$1",[d.cid]);await pool.query("INSERT INTO suppression_list(email,reason) SELECT email,'unsubscribe' FROM contacts WHERE id=$1 ON CONFLICT(email) DO UPDATE SET reason='unsubscribe'",[d.cid]);res.writeHead(200,{"content-type":"text/html; charset=utf-8"});return res.end("<main style='font:16px system-ui;max-width:560px;margin:15vh auto;padding:24px;color:#172033'><h1>You are unsubscribed</h1><p>You will no longer receive QUANTUM AI marketing emails at this address.</p></main>")}
 if(p.startsWith("/api/")){
  if(!auth(req))return send(res,401,{error:"Authentication required"});
  if(!pool)return send(res,503,{error:"Database is not configured"});
  try{
   if(p==="/api/data"&&req.method==="GET"){
    const [c,ca,e,s]=await Promise.all([pool.query("SELECT id,email,name,consent,(unsubscribed_at IS NOT NULL) AS unsub,created_at FROM contacts ORDER BY created_at DESC LIMIT 5000"),pool.query("SELECT c.id,c.name,c.subject,c.body,c.status,c.created_at,COALESCE(ev.clicks,0)::int AS clicks,COALESCE(ev.unique_clicks,0)::int AS unique_clicks FROM campaigns c LEFT JOIN (SELECT campaign_id,count(*) FILTER (WHERE event_type='click') AS clicks,count(DISTINCT contact_id) FILTER (WHERE event_type='click') AS unique_clicks FROM campaign_events GROUP BY campaign_id) ev ON ev.campaign_id=c.id ORDER BY c.created_at DESC LIMIT 100"),pool.query("SELECT count(*)::int AS sent FROM campaign_events WHERE event_type='sent'"),pool.query("SELECT key,value FROM settings")]);
    const settings=Object.fromEntries(s.rows.map(x=>[x.key,x.value]));
    return send(res,200,{contacts:c.rows,campaigns:ca.rows,sent:e.rows[0].sent,settings,providerConfigured:sesReady,dbConfigured:true});
   }
   if(p==="/api/contacts"&&req.method==="POST"){const d=await readBody(req),email=String(d.email||"").trim().toLowerCase();if(!emailOk(email))return send(res,400,{error:"Enter a valid email"});const consent=Boolean(d.consent);const r=await pool.query("INSERT INTO contacts(email,name,consent,consent_source,consent_at) VALUES($1,$2,$3,$4,CASE WHEN $3 THEN now() ELSE NULL END) ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name,consent=contacts.consent OR EXCLUDED.consent,consent_source=COALESCE(contacts.consent_source,EXCLUDED.consent_source),consent_at=COALESCE(contacts.consent_at,EXCLUDED.consent_at),updated_at=now() RETURNING id,email,name,consent,unsubscribed_at",[email,String(d.name||"").slice(0,120),consent,String(d.consentSource||"owner-entered")]);return send(res,201,{contact:r.rows[0]})}
   if(p==="/api/contacts/import"&&req.method==="POST"){const d=await readBody(req);if(!Array.isArray(d.contacts)||d.contacts.length>500)return send(res,400,{error:"Import up to 500 rows at a time"});let added=0,skipped=0;for(const x of d.contacts){const email=String(x.email||"").trim().toLowerCase();if(!emailOk(email)){skipped++;continue}const consent=Boolean(x.consent);await pool.query("INSERT INTO contacts(email,name,consent,consent_source,consent_at) VALUES($1,$2,$3,$4,CASE WHEN $3 THEN now() ELSE NULL END) ON CONFLICT(email) DO NOTHING",[email,String(x.name||"").slice(0,120),consent,consent?"csv-consent-attestation":null]);if(consent)added++;else skipped++}return send(res,200,{ok:true,consentedRowsAdded:added,unconsentedOrInvalidSkipped:skipped})}
   const delContact=p.match(/^\/api\/contacts\/([0-9a-f-]{36})$/);if(delContact&&req.method==="DELETE"){await pool.query("DELETE FROM contacts WHERE id=$1",[delContact[1]]);return send(res,200,{ok:true})}
   if(p==="/api/campaigns"&&req.method==="POST"){const d=await readBody(req);if(!String(d.name||"").trim()||!String(d.subject||"").trim()||!String(d.body||"").trim())return send(res,400,{error:"Name, subject and message are required"});const r=await pool.query("INSERT INTO campaigns(name,subject,body) VALUES($1,$2,$3) RETURNING *",[String(d.name).slice(0,120),String(d.subject).slice(0,180),String(d.body).slice(0,20000)]);return send(res,201,{campaign:r.rows[0]})}
   const delCampaign=p.match(/^\/api\/campaigns\/([0-9a-f-]{36})$/);if(delCampaign&&req.method==="DELETE"){await pool.query("DELETE FROM campaigns WHERE id=$1",[delCampaign[1]]);return send(res,200,{ok:true})}
   const sendCampaign=p.match(/^\/api\/campaigns\/([0-9a-f-]{36})\/send-batch$/);if(sendCampaign&&req.method==="POST"){
    if(!sesReady)return send(res,503,{error:"Email provider is not configured. Add approved SES credentials, verified MAIL_FROM and PUBLIC_APP_URL first."});
    const campaign=(await pool.query("SELECT * FROM campaigns WHERE id=$1",[sendCampaign[1]])).rows[0];if(!campaign)return send(res,404,{error:"Campaign not found"});
    const recipients=await pool.query("SELECT c.id,c.email,c.name FROM contacts c LEFT JOIN suppression_list s ON s.email=c.email WHERE c.consent=true AND c.unsubscribed_at IS NULL AND s.email IS NULL AND NOT EXISTS(SELECT 1 FROM campaign_events e WHERE e.campaign_id=$1 AND e.contact_id=c.id AND e.event_type='sent') ORDER BY c.created_at LIMIT 25",[campaign.id]);
    if(!recipients.rowCount)return send(res,400,{error:"No eligible, unsent, opted-in contacts"});
    let sentCount=0,failed=0;
    for(const c of recipients.rows){const unsub=token({cid:c.id,exp:Math.floor(Date.now()/1000)+60*60*24*365*2});const unsubscribeUrl=process.env.PUBLIC_APP_URL.replace(/\/$/,"")+"/unsubscribe?t="+encodeURIComponent(unsub);const trackedBody=escapeHtml(campaign.body).replace(/https?:\/\/[^\s<]+/g,match=>{let target;try{target=new URL(match.replace(/&amp;/g,"&"));if(!["http:","https:"].includes(target.protocol))return match}catch{return match}const track=token({campaignId:campaign.id,cid:c.id,url:target.toString(),exp:Math.floor(Date.now()/1000)+60*60*24*90});return `<a href="${process.env.PUBLIC_APP_URL.replace(/\/$/,"")}/track/${track}" rel="noopener noreferrer">${match}</a>`});const html=`<div style="font:16px Arial,sans-serif;line-height:1.6;color:#172033;max-width:640px;margin:auto"><p>Hi ${escapeHtml(c.name||"there")},</p><div>${trackedBody.replace(/\n/g,"<br>")}</div><hr><p style="font-size:12px;color:#667085">You receive this because you opted in to QUANTUM AI updates. <a href="${unsubscribeUrl}">Unsubscribe</a></p></div>`;try{const out=await ses.send(new SendEmailCommand({FromEmailAddress:process.env.MAIL_FROM,Destination:{ToAddresses:[c.email]},Content:{Simple:{Subject:{Data:campaign.subject,Charset:"UTF-8"},Body:{Html:{Data:html,Charset:"UTF-8"},Text:{Data:campaign.body+"\n\nUnsubscribe: "+unsubscribeUrl,Charset:"UTF-8"}}}},ListManagementOptions:{ContactListName:process.env.SES_CONTACT_LIST||undefined,TopicName:process.env.SES_TOPIC||undefined}}));await pool.query("INSERT INTO campaign_events(campaign_id,contact_id,event_type,provider_message_id) VALUES($1,$2,'sent',$3)",[campaign.id,c.id,out.MessageId||null]);sentCount++}catch(err){failed++;await pool.query("INSERT INTO campaign_events(campaign_id,contact_id,event_type,metadata) VALUES($1,$2,'failed',$3)",[campaign.id,c.id,JSON.stringify({error:String(err.message).slice(0,300)})])}}
    return send(res,200,{ok:true,sent:sentCount,failed,processed:recipients.rowCount,remaining:true,batchLimit:25});
   }
   if(p==="/api/settings"&&req.method==="POST"){const d=await readBody(req);for(const key of ["price","goal","sales"]){if(d[key]!==undefined)await pool.query("INSERT INTO settings(key,value) VALUES($1,$2::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()",[key,JSON.stringify(Number(d[key]))])}return send(res,200,{ok:true})}
   return send(res,404,{error:"Not found"});
  }catch(err){console.error("API error",err);return send(res,500,{error:"Server error. Check service logs."})}
 }
 const file=p==="/"?"index.html":decodeURIComponent(p).replace(/^\/+/, ""),target=path.resolve(publicDir,file);
 if(!target.startsWith(publicDir+path.sep)&&target!==path.join(publicDir,"index.html"))return send(res,403,{error:"Forbidden"});
 const mime={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"text/javascript; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"};
 try{const data=await readFile(target);res.writeHead(200,{"content-type":mime[path.extname(target)]||"application/octet-stream","x-content-type-options":"nosniff"});res.end(data)}catch{res.writeHead(404,{"content-type":"text/plain"});res.end("Not found")}
});
migrate().then(()=>server.listen(port,"0.0.0.0",()=>console.log("QUANTUM AI Mailer listening on "+port))).catch(err=>{console.error("Database migration failed",err);process.exit(1)});
