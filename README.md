# Agent Flow

Register LLM agents, chain them into flows, run them, and track token usage. Available in two versions that live in this repo:

| | **Full** (`full/`) | **Lite** (`lite/`) |
|---|---|---|
| Runs on | Docker (FastAPI + Streamlit + SQLite) | Any static host, e.g. GitHub Pages |
| Providers | OpenAI, Anthropic, Gemini and more, via LiteLLM | OpenAI, Anthropic, Gemini (direct from the browser) |
| Tools (calculator, web search) | Yes | No |
| Cost in USD | Yes (LiteLLM prices) | No, tokens only |
| Per-agent persistent memory + shared flow context | Yes | No |
| Live model list / type your own | Yes | Yes |
| Live run view, history, token report | Yes | Yes |
| Data storage | SQLite volume on the server | Browser `localStorage` |
| API keys | Server `.env` | Entered in the browser |

## Repository structure

```text
agent-flow/
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── pages.yml          # deploys lite/ to GitHub Pages
├── full/                      # Docker version
│   ├── backend/
│   │   ├── main.py            # FastAPI routes
│   │   ├── runner.py          # agent + flow execution, tool loop
│   │   ├── tools.py           # calculator (safe AST), web_search
│   │   ├── models.py          # SQLAlchemy tables
│   │   ├── models_live.py     # live model listing per provider
│   │   └── database.py
│   ├── frontend/
│   │   └── app.py             # Streamlit UI
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── entrypoint.sh          # starts API + UI in one container
│   ├── requirements.txt
│   ├── .env.example
│   ├── .dockerignore
│   ├── .gitignore
│   └── README.md
└── lite/                      # static version
    ├── index.html             # whole app (HTML + CSS + JS)
    └── README.md
```

## Quick start

### Full (Docker)
```bash
cd full
cp .env.example .env        # add your API keys
docker compose up --build
```
UI: http://localhost:8501 · API docs: http://localhost:8000/docs

### Lite (local preview)
```bash
cd lite
python -m http.server 8080  # then open http://localhost:8080
```

## Publish Lite on GitHub Pages
1. Push this repo to GitHub (branch `main`).
2. Go to **Settings → Pages → Source** and choose **GitHub Actions**.
3. The workflow in `.github/workflows/pages.yml` publishes the `lite/` folder at `https://<user>.github.io/<repo>/`. It runs on every push that touches `lite/`, or manually from the **Actions** tab.

Only `lite/` is published. The `full/` version needs a server and is never exposed by Pages.

## Security notes
- **Never commit `.env` or API keys.** `.gitignore` already excludes `.env`.
- **Lite** keeps keys in the visitor's browser and calls providers directly. Use your own keys with a spending limit, and only on devices you trust. The published page contains no keys.
- **Full** stores keys on the server only. If you deploy it publicly, put authentication in front of it: the app has no login.

## Known limitations
- Full: if you have a database from an earlier version, delete it (`docker compose down -v`) because the schema changed.
- Lite: web search is not possible without a server because of browser CORS rules.
