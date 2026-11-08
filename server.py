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
PERSONA = ("You are ARIM, a friendly personal AI assistant. Reply in the language "
           "the user writes in (Bangla or English). Keep answers short and clear.")

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


@app.post("/api/chat")
def chat():
    u = current_user()
    if not u:
        return jsonify(error="login"), 401
    msgs = (request.json or {}).get("messages", [])[-12:]
    if not msgs:
        return jsonify(error="empty"), 400
    last = msgs[-1]["text"].strip()
    for prefix in ("remember ", "মনে রাখো "):
        if last.lower().startswith(prefix):
            with db() as c:
                c.execute("insert into memory(uid,text) values(?,?)", (u["id"], last[len(prefix):]))
    mem = [r["text"] for r in db().execute("select text from memory where uid=?", (u["id"],))]
    system = get_setting("persona", PERSONA)
    if mem:
        system += "\nThings you know about the user: " + "; ".join(mem)
    body = {"model": AI_MODEL,
            "messages": [{"role": "system", "content": system}] +
                        [{"role": "user" if m["role"] == "user" else "assistant",
                          "content": m["text"]} for m in msgs]}
    headers = {"Authorization": "Bearer " + AI_KEY} if AI_KEY else {}
    try:
        r = requests.post(AI_URL, headers=headers, json=body, timeout=60)
        text = r.json()["choices"][0]["message"]["content"]
    except Exception:
        return jsonify(error="AI service is busy or unavailable. Try again."), 502
    return jsonify(reply=text)


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
