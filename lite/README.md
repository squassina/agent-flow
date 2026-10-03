# Agent Flow: Lite version (static)

A single `index.html`: agents, flows, runs, history and token report, all in the browser. Data and API keys are stored in `localStorage`; requests go straight to OpenAI, Anthropic and Gemini.

## Use
- Locally: `python -m http.server 8080`, then open http://localhost:8080
- On GitHub Pages: see the root README (the workflow publishes this folder).

## Limitations
- No tools (calculator, web search) and no USD cost, only tokens.
- Data is tied to one browser (`localStorage`); there is no backup/export.
- Keys live in the browser. Use your own keys, with a spending limit, on trusted devices only.
