# ARIN AI

ARIN AI is a mobile-first assistant web app with a red holographic home screen, six specialist agents, a shared team conversation, per-agent private memories, shared user memories, headlines, a photo editor, and video trimming.

## Local setup

Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open http://localhost:8000.

The existing server uses an OpenAI-compatible chat-completions endpoint. Its default is the Pollinations endpoint, so configure the provider details as environment variables if needed:

| Variable | Purpose | Default |
|---|---|---|
| `AI_URL` | OpenAI-compatible chat completions URL | `https://gen.pollinations.ai/v1/chat/completions` |
| `AI_MODEL` | Model name sent to the provider | `openai` |
| `AI_KEY` | Optional provider API key | empty |
| `ADMIN_KEY` | Secret required for admin settings changes | empty (admin disabled) |
| `ARIN_DB_PATH` | SQLite database location | `./arim.db` |

Never commit API keys or admin secrets. Put them in the hosting provider's secret environment settings or a server-only `.env` file.

## Deploy to Render

1. Import this GitHub repository as a Render Web Service, or use the included `render.yaml` blueprint.
2. Set `AI_KEY` if your chosen AI provider requires a key. The default endpoint may also change its access requirements over time.
3. Deploy. The Procfile and Render blueprint run `server:app`; `apt.txt` requests FFmpeg for the video tool.
4. Visit the deployed URL and test the assistant, memory, news, and media features.

The default SQLite database is stored in the service filesystem. If the host uses an ephemeral filesystem, attach a persistent disk and point `ARIN_DB_PATH` to a file on that disk to preserve accounts, chats, and memories across redeploys.

## Included features

- **Six agents:** ARIN (coordination), RONI (coding), DIVA (creative), ZARA (assistant), MAYA (companion), and NEXUS (analysis).
- **Shared team conversation:** selected agents can use the shared conversation as context.
- **Agent tools:** team task execution, agent-to-agent transfer, team-size preferences, and per-agent private memory APIs.
- **User memory:** add and delete shared notes from Settings; the chat also recognizes “remember …” and “মনে রাখো …” requests for the selected agent's private memory.
- **News:** BBC World RSS headlines.
- **Photo studio:** browser-based brightness, contrast, saturation, grayscale, rotate, flip, text overlay, and PNG export.
- **Video studio:** server-side FFmpeg trim with a 60 MB upload cap and 15-minute maximum clip.
- **Visual Hub:** uses an external image-generation endpoint; availability is controlled by that provider.

## Important operational notes

- AI chat depends on the configured provider being reachable and accepting the selected model.
- Video trimming requires FFmpeg to be installed on the host.
- The admin endpoint changes server-side settings; it does not deploy new source code.
- Use HTTPS and a persistent, backed-up database before storing important personal information.
