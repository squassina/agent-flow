# Agent Flow: Full version (Docker)

FastAPI backend + Streamlit UI + SQLite, running in a single container. Multi-provider via LiteLLM, with tools (calculator, web search), live run view, history, and token/cost reports.

## Run
```bash
cp .env.example .env     # OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
docker compose up --build
```
- UI: http://localhost:8501
- API docs: http://localhost:8000/docs
- Data lives in the `agent_data` volume. Reset with `docker compose down -v`.

## Run without Docker
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn main:app --reload          # terminal 1
cd frontend && streamlit run app.py              # terminal 2
```

## Notes
- Models: the Agents tab lists models live from your keys (🔄 button) and also accepts a typed model name. Gemini models need the `gemini/` prefix (e.g. `gemini/gemini-2.5-flash`).
- `backend/runner.py` runs each flow in a background task with its own DB session and records every step.
- This app has no authentication. Do not expose it publicly without a login or reverse-proxy auth.
