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

## Agent context and memory
- **Flow context mode**
  - `chain` (default): each agent receives only the output of the previous one. This is the cheapest mode.
  - `shared`: each agent receives the original request, a short summary (≈400 characters) of earlier steps, and the complete output of the previous step. Maintains context without resending everything.
- **Persistent memory per agent** (optional): after each step, the agent merges the interaction into a limited summary (`memory_max_chars`, default 1500). This summary is injected into the system prompt in subsequent runs across any flow, and is saved in the `agent_memory` table. It can be edited or cleared in the Agents tab.
- **Low-cost memory** (optional, per agent):
  - `memory_model`: model used exclusively for consolidating memory. **Empty = automatic**: selects the cheapest chat model among those available in your keys (live list) that has pricing in LiteLLM's table (weighted 3:1 input/output cost; ignores previews, audio, image, embeddings, and deprecated models). `same` = same model as the agent. Or type a specific model. Without a live list (no keys provided), it defaults to the agent's model. The current choice is shown in the Agents tab and via `GET /models/cheapest`.
  - `memory_every` (N): interactions are buffered, and memory is consolidated in a single call every N interactions (instead of once per step). If the call fails, the buffer is kept for the next attempt.
  - `memory_min_chars`: outputs shorter than this size (default 200) are ignored, as they rarely contain lasting information.
- Memory update costs are recorded with `kind=memory` (using the model selected) and appear separately in the Report.
- Legacy databases are migrated automatically (new columns added via `ALTER TABLE`).
