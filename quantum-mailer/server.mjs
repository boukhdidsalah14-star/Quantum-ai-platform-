import http from "node:http";
import { readFile } from "node:fs/promises";
import { createHmac, timingSafeEqual } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(__dirname, "public");
const port = Number(process.env.PORT || 3000);
const adminPassword = process.env.ADMIN_PASSWORD || "";
const sessionSecret = process.env.SESSION_SECRET || "";
const sessionTtl = 8 * 60 * 60;

function sign(value) {
  return createHmac("sha256", sessionSecret).update(value).digest("base64url");
}
function makeToken() {
  const payload = Buffer.from(JSON.stringify({ exp: Math.floor(Date.now()/1000) + sessionTtl })).toString("base64url");
  return payload + "." + sign(payload);
}
function validToken(token) {
  if (!token || !sessionSecret) return false;
  const [payload, signature] = token.split(".");
  if (!payload || !signature) return false;
  const expected = sign(payload);
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a,b)) return false;
  try { return JSON.parse(Buffer.from(payload,"base64url").toString()).exp > Math.floor(Date.now()/1000); }
  catch { return false; }
}
function cookies(req) {
  return Object.fromEntries((req.headers.cookie || "").split(";").map(v=>v.trim()).filter(Boolean).map(v=>{
    const i=v.indexOf("="); return [v.slice(0,i),decodeURIComponent(v.slice(i+1))];
  }));
}
function send(res,status,body,headers={}) {
  res.writeHead(status,{"content-type":"application/json; charset=utf-8","cache-control":"no-store",...headers});
  res.end(JSON.stringify(body));
}
async function body(req) {
  let raw=""; for await (const chunk of req) { raw+=chunk; if(raw.length>20000) throw new Error("Request too large"); }
  return raw ? JSON.parse(raw) : {};
}
const mime={".html":"text/html; charset=utf-8",".css":"text/css; charset=utf-8",".js":"text/javascript; charset=utf-8",".svg":"image/svg+xml",".webmanifest":"application/manifest+json"};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,"http://localhost");
  if(url.pathname==="/api/health") return send(res,200,{ok:true,app:"QUANTUM AI Mailer",version:"0.1.0",providerConfigured:Boolean(process.env.AWS_ACCESS_KEY_ID && process.env.AWS_SECRET_ACCESS_KEY && process.env.MAIL_FROM)});
  if(url.pathname==="/api/auth/status") return send(res,200,{authenticated:validToken(cookies(req).qmail_session),passwordConfigured:Boolean(adminPassword && sessionSecret)});
  if(url.pathname==="/api/login" && req.method==="POST"){
    if(!adminPassword || !sessionSecret) return send(res,503,{error:"Owner login is not configured. Set ADMIN_PASSWORD and SESSION_SECRET in service environment variables."});
    try {
      const data=await body(req);
      const supplied=Buffer.from(String(data.password||""));
      const expected=Buffer.from(adminPassword);
      if(supplied.length!==expected.length || !timingSafeEqual(supplied,expected)) return send(res,401,{error:"Incorrect password"});
      return send(res,200,{ok:true},{ "set-cookie":`qmail_session=${encodeURIComponent(makeToken())}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${sessionTtl}${process.env.NODE_ENV==="production"?"; Secure":""}` });
    } catch { return send(res,400,{error:"Invalid request"}); }
  }
  if(url.pathname==="/api/logout" && req.method==="POST") return send(res,200,{ok:true},{"set-cookie":"qmail_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"});
  if(url.pathname.startsWith("/api/")) return send(res,404,{error:"Not found"});
  const file=url.pathname==="/" ? "index.html" : decodeURIComponent(url.pathname).replace(/^\/+/, "");
  const target=path.resolve(publicDir,file);
  if(!target.startsWith(publicDir + path.sep) && target!==path.join(publicDir,"index.html")) return send(res,403,{error:"Forbidden"});
  try { const data=await readFile(target); res.writeHead(200,{"content-type":mime[path.extname(target)]||"application/octet-stream","x-content-type-options":"nosniff"}); res.end(data); }
  catch { res.writeHead(404,{"content-type":"text/plain"}); res.end("Not found"); }
});
server.listen(port,"0.0.0.0",()=>console.log(`QUANTUM AI Mailer listening on ${port}`));
