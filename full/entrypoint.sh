#!/usr/bin/env bash
# Sobe API e UI no mesmo container (sem depender de DNS entre serviços).
uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port 8000 &
streamlit run /app/frontend/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true &
wait -n
exit $?
