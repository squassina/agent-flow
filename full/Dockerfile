FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    API_URL=http://localhost:8000 \
    DATABASE_URL=sqlite:////data/agent_flow.db
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY entrypoint.sh .

RUN useradd -m appuser && mkdir /data && chown appuser /data && chmod +x entrypoint.sh
USER appuser

EXPOSE 8000 8501
CMD ["./entrypoint.sh"]
