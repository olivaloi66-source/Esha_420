# ARIN AI

ARIN AI is a Flask-backed assistant web app with a responsive red holographic home screen, six selectable agent personas, a shared chat, saved memories, RSS headlines, a photo editor, and optional FFmpeg video trimming.

## Run locally

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key"
export ARIN_ADMIN_KEY="choose-a-long-random-secret"
python app.py
```

Open http://localhost:5000. On Windows, activate the virtual environment with `.venv\\Scripts\\activate` and set environment variables using PowerShell's `$env:NAME="value"` syntax.

## Deploy on Render

1. Push this repository to GitHub and create a new Render Web Service from it (or use the included `render.yaml` blueprint).
2. Set the secret `OPENAI_API_KEY` in the Render environment. The blueprint prompts for it; it is never stored in source control.
3. Deploy. Render uses `gunicorn` and the included `apt.txt` requests FFmpeg for video trimming.
4. Open the deployed URL and test chat, memory, and media tools.

Environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | Required to enable AI chat | unset |
| `OPENAI_MODEL` | Chat model name | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | OpenAI-compatible API base URL | `https://api.openai.com/v1` |
| `ARIN_ADMIN_KEY` | Protects the admin version endpoint | unset (admin disabled) |
| `ARIN_VERSION` | Version shown in the app | `1.0.0` |
| `ARIN_RELEASE_NOTES` | Update banner text | empty |
| `ARIN_DB_PATH` | SQLite database file | `./arin.sqlite3` |

## Features and limitations

- **Agents:** ARIN, RONI, DIVA, ZARA, MAYA, and NEXUS use different system instructions; they share the same conversation in the browser.
- **Memory:** saved memories are scoped to the browser session token and can be deleted from Settings. Clearing browser storage or losing the SQLite database loses access to that session's memories.
- **News:** headline titles are fetched from BBC World and Technology RSS feeds.
- **Photo studio:** brightness, contrast, saturation, grayscale, rotation, flip, text overlay, and PNG export run in the browser.
- **Video studio:** trimming is server-side and requires FFmpeg. Uploads are limited to 100 MB and clips to 15 minutes.
- **Visual Hub:** uses the external Pollinations image endpoint; its availability and policies are controlled by that provider.
- **Admin update:** changes the running process's displayed version only; it does not deploy code or persist across a restart.

## Production notes

Use HTTPS, keep API/admin keys in the host's secret environment settings, and never commit secrets. The default SQLite path is local to the service; on hosts with ephemeral filesystems, configure `ARIN_DB_PATH` on a persistent mounted disk if saved memories must survive restarts. Configure backups and access controls before using this with real personal data.
