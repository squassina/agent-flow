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

## Contexto e memória dos agentes
- **Modo de contexto do fluxo**
  - `chain` (padrão): cada agente recebe só a saída do anterior. É o mais barato.
  - `shared`: cada agente recebe o pedido original, um resumo curto (≈400 caracteres) dos passos mais antigos e a saída completa do passo anterior. Mantém o contexto sem reenviar tudo.
- **Memória persistente por agente** (opcional): após cada passo, o agente funde a interação em um resumo limitado (`memory_max_chars`, padrão 1500). Esse resumo é injetado no system prompt nas próximas execuções, em qualquer fluxo, e fica salvo na tabela `agent_memory`. Pode ser editado ou limpo na aba Agentes.
- **Memória barata** (opcional, por agente):
  - `memory_model`: modelo usado só para consolidar a memória. **Vazio = automático**: escolhe o modelo de chat mais barato entre os disponíveis nas suas chaves (lista ao vivo) que tenha preço na tabela do LiteLLM (custo ponderado 3:1 entrada/saída; ignora previews, áudio, imagem, embeddings e modelos descontinuados). `same` = mesmo modelo do agente. Ou digite um modelo específico. Sem lista ao vivo (sem chaves), usa o modelo do agente. A escolha atual aparece na aba Agentes e em `GET /models/cheapest`.
  - `memory_every` (N): as interações ficam num buffer e a memória é consolidada em uma única chamada a cada N interações (em vez de uma por passo). Se a chamada falhar, o buffer é mantido para a próxima tentativa.
  - `memory_min_chars`: saídas menores que esse tamanho (padrão 200) são ignoradas, pois raramente têm informação duradoura.
- O custo da atualização da memória é registrado como `kind=memory` (com o modelo usado) e aparece separado no Relatório.
- Bancos antigos são migrados automaticamente (colunas novas via `ALTER TABLE`).
