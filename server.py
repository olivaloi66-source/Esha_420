import os, sqlite3, hashlib, secrets, subprocess, tempfile, requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, send_from_directory, send_file

# Load secrets from .env (kept on the server only, never sent to the app)
if os.path.exists(".env"):
    for line in open(".env"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

AI_URL = os.environ.get("AI_URL", "https://gen.pollinations.ai/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "openai")
AI_KEY = os.environ.get("AI_KEY", "")  # optional; leave empty for key-free services
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
PERSONA = ("You are ARIN, a friendly personal AI assistant. Reply in the language "
           "the user writes in (Bangla or English). Keep answers clear and useful.")
AGENTS = {
    "RONI": "You are Roni, ARIN Town's coding and engineering agent. Think like a careful software engineer.",
    "DIVA": "You are Diva, ARIN Town's creative design and writing agent. Think visually and creatively.",
    "ZARA": "You are Zara, ARIN Town's personal assistant and organizer. Be practical and attentive.",
    "MAYA": "You are Maya, ARIN Town's companion and communication agent. Be warm, thoughtful, and respectful.",
    "ARIN": "You are Arin, the lead research and coordination agent. Be accurate, balanced, and clear.",
    "NEXUS": "You are Nexus, ARIN Town's analysis and strategy agent. Reason systematically and check assumptions."
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB uploads


def db():
    c = sqlite3.connect("arim.db")
    c.row_factory = sqlite3.Row
    return c


with db() as c:
    c.executescript(
        "create table if not exists users(id integer primary key, name text unique, salt text, pw text, token text);"
        "create table if not exists memory(id integer primary key, uid int, text text);"
        "create table if not exists settings(k text primary key, v text);"
        "create table if not exists agent_memory(id integer primary key, uid int not null, agent text not null, text text not null, created_at text default current_timestamp);"
        "create table if not exists agent_shared_chat(id integer primary key, uid int not null, speaker text not null, text text not null, created_at text default current_timestamp);"
    )


def get_setting(k, default=""):
    r = db().execute("select v from settings where k=?", (k,)).fetchone()
    return r["v"] if r else default


def set_setting(k, v):
    with db() as c:
        c.execute("insert or replace into settings(k,v) values(?,?)", (k, v))


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()


def current_user():
    t = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not t:
        return None
    return db().execute("select * from users where token=?", (t,)).fetchone()


@app.get("/")
def home():
    return send_from_directory(".", "index.html")


@app.get("/arin-agent-town.css")
def agent_town_stylesheet():
    return send_from_directory(".", "arin-agent-town.css", mimetype="text/css")


@app.post("/api/start")
def start():
    # No password: every device gets its own private token automatically.
    token = secrets.token_hex(24)
    with db() as c:
        c.execute("insert into users(name,salt,pw,token) values(?,?,?,?)",
                  ("u_" + token[:10], "", "", token))
    return jsonify(token=token)


@app.get("/api/version")
def version():
    return jsonify(version=get_setting("version", "1"), notes=get_setting("notes", ""))


def call_model(system, messages):
    body = {"model": AI_MODEL, "messages": [{"role": "system", "content": system}] + messages}
    headers = {"Authorization": "Bearer " + AI_KEY} if AI_KEY else {}
    r = requests.post(AI_URL, headers=headers, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def valid_agent(name):
    name = str(name or "ARIN").upper()
    return name if name in AGENTS else None


@app.get("/api/agents")
def agents_list():
    return jsonify(agents=[{"id": k, "name": k.title(), "role": v} for k, v in AGENTS.items()])


@app.get("/api/agents/<agent>/memory")
def agent_memory_list(agent):
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    name = valid_agent(agent)
    if not name:
        return jsonify(error="unknown agent"), 404
    rows = db().execute("select id,text,created_at from agent_memory where uid=? and agent=? order by id desc",
                        (u["id"], name)).fetchall()
    return jsonify(agent=name, items=[dict(r) for r in rows])


@app.post("/api/agents/<agent>/memory")
def agent_memory_add(agent):
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    name = valid_agent(agent)
    if not name:
        return jsonify(error="unknown agent"), 404
    value = str((request.json or {}).get("text", "")).strip()
    if not value or len(value) > 4000:
        return jsonify(error="text must be 1-4000 characters"), 400
    with db() as c:
        cur = c.execute("insert into agent_memory(uid,agent,text) values(?,?,?)", (u["id"], name, value))
    return jsonify(ok=True, id=cur.lastrowid, agent=name)


@app.delete("/api/agents/<agent>/memory/<int:mid>")
def agent_memory_delete(agent, mid):
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    name = valid_agent(agent)
    if not name:
        return jsonify(error="unknown agent"), 404
    with db() as c:
        c.execute("delete from agent_memory where id=? and uid=? and agent=?", (mid, u["id"], name))
    return jsonify(ok=True)


@app.post("/api/chat")
def chat():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    data = request.json or {}
    name = valid_agent(data.get("agent", "ARIN"))
    if not name:
        return jsonify(error="unknown agent"), 400
    msgs = data.get("messages", [])[-12:]
    if not msgs:
        return jsonify(error="empty"), 400
    last = str(msgs[-1].get("text", "")).strip()
    for prefix in ("remember ", "মনে রাখো "):
        if last.lower().startswith(prefix):
            with db() as c:
                c.execute("insert into agent_memory(uid,agent,text) values(?,?,?)",
                          (u["id"], name, last[len(prefix):]))
    # The conversation is shared with all six agents; private memories remain isolated.
    with db() as c:
        c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)", (u["id"], "USER", last))
    shared_chat = db().execute(
        "select speaker,text from agent_shared_chat where uid=? order by id desc limit 40", (u["id"],)).fetchall()
    general = [r["text"] for r in db().execute("select text from memory where uid=?", (u["id"],))]
    private = [r["text"] for r in db().execute(
        "select text from agent_memory where uid=? and agent=? order by id desc limit 30", (u["id"], name))]
    system = get_setting("persona", PERSONA) + "\n\n" + AGENTS[name]
    system += "\nAll six agents are silent listeners to this same shared conversation. You are the selected speaking agent. Other agents can use this shared conversation as context, but their private memories are not shared."
    system += "\nYou may recommend handing a task to another named agent when useful; do not claim a handoff happened unless the user or interface confirms it."
    if general:
        system += "\nShared user notes: " + "; ".join(general[-30:])
    if private:
        system += "\nYour private memories: " + "; ".join(reversed(private))
    context = [{"role": "user" if r["speaker"] == "USER" else "assistant",
                "content": "[" + r["speaker"] + "] " + r["text"]} for r in reversed(shared_chat)]
    try:
        answer = call_model(system, context[-40:])
    except Exception:
        return jsonify(error="AI service is busy or unavailable. Check AI_URL / AI_KEY."), 502
    with db() as c:
        c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)", (u["id"], name, answer))
    return jsonify(reply=answer, agent=name, shared_with=list(AGENTS.keys()))


@app.post("/api/team/run")
def team_run():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    data = request.json or {}
    task = str(data.get("task", "")).strip()
    chosen = []
    for raw in data.get("agents", []):
        name = valid_agent(raw)
        if name and name not in chosen:
            chosen.append(name)
    if not task or len(task) > 8000:
        return jsonify(error="task must be 1-8000 characters"), 400
    if not chosen:
        return jsonify(error="select at least one agent"), 400
    if len(chosen) > 6:
        return jsonify(error="maximum six agents"), 400
    with db() as c:
        c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)",
                  (u["id"], "USER", "TEAM TASK: " + task))
    shared = [r["text"] for r in db().execute("select text from memory where uid=?", (u["id"],))]
    history = db().execute(
        "select speaker,text from agent_shared_chat where uid=? order by id desc limit 40", (u["id"],)).fetchall()
    team_context = [{"role": "user" if r["speaker"] == "USER" else "assistant",
                     "content": "[" + r["speaker"] + "] " + r["text"]} for r in reversed(history)]
    results = []
    for name in chosen:
        private = [r["text"] for r in db().execute(
            "select text from agent_memory where uid=? and agent=? order by id desc limit 20", (u["id"], name))]
        system = get_setting("persona", PERSONA) + "\n\n" + AGENTS[name]
        system += "\nYou are participating in a multi-agent team. Build on earlier agents' findings, check their work, and state uncertainty."
        system += "\nAll team contributions and the shared user conversation are visible to you. Your private memories are visible only to you."
        if shared:
            system += "\nShared user notes: " + "; ".join(shared[-20:])
        if private:
            system += "\nYour private memories: " + "; ".join(reversed(private))
        prompt = "Work on this team task: " + task + ". Use the previous agents' contributions in the conversation as context."
        try:
            contribution = call_model(system, (team_context + [{"role": "user", "content": prompt}])[-40:])
        except Exception:
            return jsonify(error="Team stopped: AI service failed while " + name + " was working.", completed=results), 502
        results.append({"agent": name, "reply": contribution})
        with db() as c:
            c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)",
                      (u["id"], name, contribution))
        team_context.append({"role": "assistant", "content": "[" + name + "] " + contribution})
    return jsonify(task=task, team=chosen, team_size=len(chosen), final=results[-1]["reply"], contributions=results)


@app.post("/api/agents/transfer")
def agent_transfer():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    data = request.json or {}
    source, target = valid_agent(data.get("from")), valid_agent(data.get("to"))
    task = str(data.get("task", "")).strip()
    if not source or not target or source == target:
        return jsonify(error="choose two different valid agents"), 400
    if not task or len(task) > 8000:
        return jsonify(error="task must be 1-8000 characters"), 400
    with db() as c:
        c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)",
                  (u["id"], source, "TRANSFER to " + target + ": " + task))
    shared = db().execute(
        "select speaker,text from agent_shared_chat where uid=? order by id desc limit 40", (u["id"],)).fetchall()
    private = [r["text"] for r in db().execute(
        "select text from agent_memory where uid=? and agent=? order by id desc limit 30", (u["id"], target))]
    system = get_setting("persona", PERSONA) + "\n\n" + AGENTS[target]
    system += "\nYou received a task transferred by " + source + ". Continue the work, use the shared conversation for context, and clearly report your result."
    if private:
        system += "\nYour private memories: " + "; ".join(reversed(private))
    messages = [{"role": "user" if r["speaker"] == "USER" else "assistant",
                 "content": "[" + r["speaker"] + "] " + r["text"]}
                for r in reversed(shared)]
    messages.append({"role": "user", "content": "Please take ownership of this transferred task: " + task})
    try:
        answer = call_model(system, messages[-41:])
    except Exception:
        return jsonify(error="Transfer failed: AI service is unavailable."), 502
    with db() as c:
        c.execute("insert into agent_shared_chat(uid,speaker,text) values(?,?,?)",
                  (u["id"], target, answer))
    return jsonify(ok=True, from_agent=source, to_agent=target, reply=answer)


@app.post("/api/agents/preferences")
def agent_preferences():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    try:
        count = max(1, min(6, int((request.json or {}).get("team_size", 2))))
    except (TypeError, ValueError):
        return jsonify(error="team_size must be 1-6"), 400
    set_setting("user_" + str(u["id"]) + "_team_size", str(count))
    return jsonify(ok=True, team_size=count)


@app.get("/api/agents/preferences")
def get_agent_preferences():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    count = int(get_setting("user_" + str(u["id"]) + "_team_size", "6"))
    return jsonify(team_size=max(1, min(6, count)))


@app.get("/api/memory")
def memory_list():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    rows = db().execute("select id,text from memory where uid=?", (u["id"],)).fetchall()
    return jsonify(items=[dict(r) for r in rows])


@app.delete("/api/memory/<int:mid>")
def memory_delete(mid):
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    with db() as c:
        c.execute("delete from memory where id=? and uid=?", (mid, u["id"]))
    return jsonify(ok=True)


@app.post("/api/admin/set")
def admin_set():
    if not ADMIN_KEY or request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify(error="forbidden"), 403
    d = request.json or {}
    for k in ("version", "notes", "persona"):
        if k in d:
            set_setting(k, str(d[k]))
    return jsonify(ok=True)


@app.get("/api/news")
def news():
    try:
        r = requests.get("https://feeds.bbci.co.uk/news/world/rss.xml", timeout=15)
        items = [i.findtext("title") for i in ET.fromstring(r.content).iter("item")][:8]
    except Exception:
        items = []
    return jsonify(items=items)


@app.post("/api/video/trim")
def video_trim():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    f = request.files.get("file")
    if not f:
        return jsonify(error="no file"), 400
    try:
        start = float(request.form.get("start") or 0)
        end = float(request.form.get("end") or 0)
    except ValueError:
        return jsonify(error="bad time"), 400
    d = tempfile.mkdtemp()
    src, out = os.path.join(d, "in"), os.path.join(d, "out.mp4")
    f.save(src)
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", src]
    if end > start:
        cmd += ["-t", str(end - start)]
    if request.form.get("mute") == "1":
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-movflags", "+faststart", out]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except Exception:
        return jsonify(error="Video edit failed. Is ffmpeg installed?"), 500
    return send_file(out, mimetype="video/mp4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
