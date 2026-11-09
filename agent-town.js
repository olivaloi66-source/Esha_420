(()=>{
const $=id=>document.getElementById(id);
let active=localStorage.getItem("arin.agent")||"ARIN", muted=false;
const names=["RONI","DIVA","ZARA","MAYA","ARIN","NEXUS"];
function api(path,opts={}){return fetch(path,{...opts,headers:{...(opts.body?{"Content-Type":"application/json"}:{}),...(localStorage.t?{Authorization:"Bearer "+localStorage.t}:{}),...(opts.headers||{})}})}
async function json(path,opts){const r=await api(path,opts);return r.json().catch(()=>({}));}
function addChatControls(){
 const chat=$("pv"); if(!chat||$("arinAgentSelect"))return;
 const bar=document.createElement("div");bar.className="row";bar.style.margin="0 0 8px";
 bar.innerHTML='<label style="font-size:11px;color:var(--m);white-space:nowrap">TALK TO</label><select id="arinAgentSelect" style="flex:1;background:#06121b;color:#67eaff;border:1px solid #22d3ee;border-radius:8px;padding:8px"></select><button class="btn" id="arinMute">MUTE</button>';
 names.forEach(n=>{const o=document.createElement("option");o.value=n;o.textContent=n;bar.querySelector("select").append(o)});
 bar.querySelector("select").value=active;bar.querySelector("select").onchange=e=>{active=e.target.value;localStorage.setItem("arin.agent",active);window.msgs=[];$("log").innerHTML="";$("st").textContent="● "+active+" selected"};
 bar.querySelector("#arinMute").onclick=()=>{muted=!muted;bar.querySelector("#arinMute").textContent=muted?"UNMUTE":"MUTE";if(muted&&window.speechSynthesis)speechSynthesis.cancel()};
 chat.insertBefore(bar,chat.firstChild);
}
function addSettings(){
 const section=$("s-more");if(!section||$("arinAgentSettings"))return;
 const panel=document.createElement("div");panel.id="arinAgentSettings";panel.style.cssText="margin-top:18px;padding-top:12px;border-top:1px solid #1d5268";
 panel.innerHTML='<div class="ttl mono">SIX AGENT MEMORY & TEAM</div><p style="font-size:12px;color:var(--m)">প্রতিটি Agent-এর আলাদা private memory ও নিজস্ব role থাকবে।</p><label style="font-size:12px;color:var(--a)">Agent memory</label><select id="arinMemAgent" style="margin:7px 0"></select><div id="arinMemList" style="font-size:12px;color:var(--m)">Loading…</div><div class="row"><input id="arinMemText" placeholder="শুধু এই Agent-এর জন্য memory লিখুন"><button class="btn" id="arinMemSave">SAVE</button></div><div class="ttl mono" style="margin-top:18px">TEAM COLLABORATION</div><label style="font-size:12px;color:var(--a)">একসাথে কাজ করবে কতজন?</label><select id="arinTeamCount" style="margin:7px 0"><option value="1">১ জন</option><option value="2">২ জন</option><option value="3">৩ জন</option><option value="4">৪ জন</option><option value="5">৫ জন</option><option value="6">৬ জন</option></select><div id="arinTeamChecks" style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px"></div><textarea id="arinTeamTask" rows="3" placeholder="ছয়জনের মধ্যে যাদের নিয়ে কাজ করাতে চান, কাজটি লিখুন" style="margin-top:8px"></textarea><button class="btn" id="arinTeamRun" style="margin-top:8px">START TEAM TASK</button><div id="arinTeamOut" style="font-size:12px;white-space:pre-wrap;margin-top:10px;color:#c5f7ff"></div>';
 section.append(panel);
 const sel=$("arinMemAgent");names.forEach(n=>{let o=document.createElement("option");o.value=n;o.textContent=n;sel.append(o)});
 names.forEach((n,i)=>{const l=document.createElement("label");l.innerHTML='<input type="checkbox" value="'+n+'" style="width:auto" '+(i<2?'checked':'')+'> '+n; $("arinTeamChecks").append(l)});
 sel.onchange=loadMemory;$("arinMemSave").onclick=saveMemory;$("arinTeamCount").onchange=savePreference;$("arinTeamRun").onclick=runTeam;
 loadMemory();loadPreference();
}
async function loadMemory(){const n=$("arinMemAgent").value,j=await json("/api/agents/"+n+"/memory");const box=$("arinMemList");box.innerHTML="";(j.items||[]).forEach(x=>{const row=document.createElement("div");row.style.cssText="padding:6px 0;border-bottom:1px solid #173344";const t=document.createElement("span");t.textContent=x.text+" ";const b=document.createElement("button");b.className="btn";b.textContent="delete";b.style.padding="2px 7px";b.onclick=async()=>{await api("/api/agents/"+n+"/memory/"+x.id,{method:"DELETE"});loadMemory()};row.append(t,b);box.append(row)});if(!box.children.length)box.textContent="এই Agent-এর কোনো memory এখনো সংরক্ষিত নেই।"}
async function saveMemory(){const n=$("arinMemAgent").value,t=$("arinMemText").value.trim();if(!t)return;const j=await json("/api/agents/"+n+"/memory",{method:"POST",body:JSON.stringify({text:t})});if(j.ok){$("arinMemText").value="";loadMemory()}else alert(j.error||"Save failed")}
async function savePreference(){await json("/api/agents/preferences",{method:"POST",body:JSON.stringify({team_size:Number($("arinTeamCount").value)})})}
async function loadPreference(){const j=await json("/api/agents/preferences");if(j.team_size)$("arinTeamCount").value=String(j.team_size)}
async function runTeam(){const task=$("arinTeamTask").value.trim(),count=Number($("arinTeamCount").value),agents=[...$("arinTeamChecks").querySelectorAll("input:checked")].map(x=>x.value).slice(0,count);if(!task||!agents.length){alert("কাজ লিখুন এবং অন্তত একজন Agent নির্বাচন করুন।");return}$("arinTeamOut").textContent="Agents are collaborating…";const j=await json("/api/team/run",{method:"POST",body:JSON.stringify({task,agents})});$("arinTeamOut").textContent=j.contributions?j.contributions.map(x=>x.agent+"\n"+x.reply).join("\n\n"):j.error||"Team task failed."}
const originalSpeak=window.speak;if(typeof originalSpeak==="function")window.speak=function(t){if(!muted)originalSpeak(t)};
const originalSend=window.send;if(typeof originalSend==="function")window.send=async function(text){text=(text||$("t").value).trim();if(!text)return;$("t").value="";if(typeof window.go==="function")go(innerWidth<900?"chat":document.body.dataset.v);add("user",text);msgs.push({role:"user",text});$("st").textContent="● "+active+" is thinking";const j=await json("/api/chat",{method:"POST",body:JSON.stringify({messages:msgs,agent:active})});const reply=j.reply||j.error||"AI service unavailable";add("model",reply);msgs.push({role:"model",text:reply});$("st").textContent="● "+active+" is ready";if(j.reply&&!muted)speak(reply);if(j.reply)memory(true)};
function init(){document.querySelectorAll('button[aria-label="Mic"],button[onclick="mic()"]').forEach(x=>x.remove());addChatControls();addSettings()}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();