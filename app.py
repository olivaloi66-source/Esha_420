import os
import re
import json
import time
import uuid
import sqlite3
import secrets
import tempfile
import subprocess
from pathlib import Path
from functools import wraps
from xml.etree import ElementTree as ET

import requests
from flask import Flask, jsonify, request, send_file, make_response

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ARIN_DB_PATH", ROOT / "arin.sqlite3"))
APP_VERSION = os.environ.get("ARIN_VERSION", "1.0.0")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
ADMIN_KEY = os.environ.get("ARIN_ADMIN_KEY", "")
MAX_VIDEO_BYTES = 100 * 1024 * 1024

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES + 1024 * 1024


def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_memories_token ON memories(token)")


def current_token():
    token = request.headers.get("Authorization", "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token if re.fullmatch(r"[A-Za-z0-9_-]{24,100}", token or "") else None


def require_token(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = current_token()
        if not token:
            return jsonify(error="Session expired. Refresh the page and try again."), 401
        return fn(token, *args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cache-Control"] = "no-store" if request.path.startswith("/api/") else "public, max-age=300"
    return response


@app.get("/")
def home():
    return send_file(ROOT / "index.html")


@app.post("/api/start")
def start_session():
    return jsonify(token=secrets.token_urlsafe(32))


AGENT_PROMPTS = {
    "ARIN": "You are ARIN, the main coordinator. Be helpful, accurate, concise, and transparent.",
    "RONI": "You are RONI, a senior software developer. Help with coding, debugging, architecture, and secure implementation.",
    "DIVA": "You are DIVA, a creative partner. Help with writing, visual concepts, branding, and creative work.",
    "ZARA": "You are ZARA, a practical personal assistant. Help organize tasks, plans, and clear next steps.",
    "MAYA": "You are MAYA, a warm and respectful companion. Listen carefully and respond naturally.",
    "NEXUS": "You are NEXUS, an analytical researcher. Explain reasoning, compare options, and distinguish facts from uncertainty.",
}


@app.post("/api/chat")
@require_token
def chat(token):
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    agent = str(body.get("agent", "ARIN")).upper()
    if agent not in AGENT_PROMPTS:
        agent = "ARIN"
    if not isinstance(messages, list) or not messages:
        return jsonify(error="Please enter a message."), 400
    clean = []
    for item in messages[-30:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("text", item.get("content", ""))
        if role not in ("user", "model", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        clean.append({"role": "assistant" if role in ("model", "assistant") else "user", "content": content[:12000]})
    if not clean or clean[-1]["role"] != "user":
        return jsonify(error="Send a user message to continue."), 400
    if not OPENAI_API_KEY:
        return jsonify(error="ARIN AI is not connected yet. The site owner must add OPENAI_API_KEY in the hosting environment variables."), 503

    system = AGENT_PROMPTS[agent] + " Reply in the same language as the user's latest message. If the user writes Bengali, answer in natural Bengali. Never claim to have performed actions you did not perform."
    try:
        response = requests.post(
            OPENAI_BASE_URL + "/chat/completions",
            headers={"Authorization": "Bearer " + OPENAI_API_KEY, "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL, "messages": [{"role": "system", "content": system}] + clean, "temperature": 0.7},
            timeout=(10, 90),
        )
        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            app.logger.warning("AI provider returned %s: %s", response.status_code, detail[:300])
            return jsonify(error="AI service error. Check the API key, model access, and billing settings."), 502
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        if isinstance(answer, list):
            answer = "".join(part.get("text", "") for part in answer if isinstance(part, dict))
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty model response")
        return jsonify(reply=answer.strip())
    except requests.Timeout:
        return jsonify(error="ARIN took too long to respond. Please try again."), 504
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        app.logger.exception("Chat request failed")
        return jsonify(error="Could not reach the AI service. Please try again shortly."), 502


@app.route("/api/memory", methods=["GET", "POST"])
@require_token
def memories(token):
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        text = body.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="Memory text is required."), 400
        if len(text) > 2000:
            return jsonify(error="Memory is too long (maximum 2,000 characters)."), 400
        with db() as con:
            cur = con.execute("INSERT INTO memories(token,text,created_at) VALUES(?,?,?)", (token, text.strip(), int(time.time())))
            return jsonify(id=cur.lastrowid, text=text.strip()), 201
    with db() as con:
        rows = con.execute("SELECT id,text,created_at FROM memories WHERE token=? ORDER BY id DESC LIMIT 100", (token,)).fetchall()
    return jsonify(items=[dict(row) for row in rows])


@app.delete("/api/memory/<int:memory_id>")
@require_token
def delete_memory(token, memory_id):
    with db() as con:
        cur = con.execute("DELETE FROM memories WHERE id=? AND token=?", (memory_id, token))
    return jsonify(ok=True, deleted=cur.rowcount == 1)


@app.get("/api/news")
def news():
    feeds = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ]
    items = []
    for url in feeds:
        try:
            response = requests.get(url, timeout=7, headers={"User-Agent": "ARIN-AI-News/1.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for node in root.findall(".//item"):
                title = (node.findtext("title") or "").strip()
                if title and title not in items:
                    items.append(title[:240])
                if len(items) >= 12:
                    break
        except (requests.RequestException, ET.ParseError):
            app.logger.info("News feed unavailable: %s", url)
        if len(items) >= 12:
            break
    return jsonify(items=items)


@app.get("/api/version")
def version():
    return jsonify(version=APP_VERSION, notes=os.environ.get("ARIN_RELEASE_NOTES", ""))


@app.post("/api/admin/set")
def admin_set():
    if not ADMIN_KEY:
        return jsonify(ok=False, error="Admin updates are disabled on this server."), 503
    supplied = request.headers.get("X-Admin-Key", "")
    if not secrets.compare_digest(supplied, ADMIN_KEY):
        return jsonify(ok=False, error="Invalid admin key."), 403
    body = request.get_json(silent=True) or {}
    version_value = str(body.get("version", "")).strip()
    notes = str(body.get("notes", "")).strip()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,39}", version_value):
        return jsonify(ok=False, error="Invalid version format."), 400
    # Runtime metadata is deliberately not written to source files.
    os.environ["ARIN_VERSION"] = version_value
    os.environ["ARIN_RELEASE_NOTES"] = notes[:500]
    global APP_VERSION
    APP_VERSION = version_value
    return jsonify(ok=True, version=APP_VERSION, notes=notes[:500])


@app.post("/api/video/trim")
@require_token
def trim_video(token):
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify(error="Choose a video first."), 400
    if not uploaded.mimetype.startswith("video/"):
        return jsonify(error="The uploaded file must be a video."), 415
    try:
        start = float(request.form.get("start", "0"))
        end = float(request.form.get("end", "0"))
    except ValueError:
        return jsonify(error="Enter valid start and end times."), 400
    if start < 0 or end <= start or end - start > 900:
        return jsonify(error="End time must be after start time; clips are limited to 15 minutes."), 400
    if not __import__("shutil").which("ffmpeg"):
        return jsonify(error="Video trimming is unavailable because FFmpeg is not installed on this server."), 501
    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"):
        suffix = ".mp4"
    workdir = tempfile.mkdtemp(prefix="arin-video-")
    source = Path(workdir) / ("input" + suffix)
    output = Path(workdir) / "trimmed.mp4"
    try:
        uploaded.save(source)
        if source.stat().st_size > MAX_VIDEO_BYTES:
            return jsonify(error="Video exceeds the 100 MB limit."), 413
        command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-i", str(source), "-t", str(end-start), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
        if request.form.get("mute") == "1":
            command += ["-an"]
        command += ["-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, timeout=240)
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            app.logger.warning("FFmpeg trim failed: %s", result.stderr.decode("utf-8", "ignore")[-1000:])
            return jsonify(error="Could not trim this video. Check the selected time range and file format."), 422
        response = make_response(send_file(output, mimetype="video/mp4", as_attachment=True, download_name="arin-video.mp4"))
        response.call_on_close(lambda: __import__("shutil").rmtree(workdir, ignore_errors=True))
        return response
    except subprocess.TimeoutExpired:
        return jsonify(error="Video processing took too long. Try a shorter clip."), 504
    finally:
        # Successful responses are cleaned up by call_on_close.
        if not output.exists():
            __import__("shutil").rmtree(workdir, ignore_errors=True)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Upload is too large. Maximum video size is 100 MB."), 413


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify(error="API endpoint not found."), 404
    return "Not found", 404


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
