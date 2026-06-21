# Samuel LiveKit agent worker (Phase 0 prod).
# Build context: SAM repo root (see render.yaml dockerContext).

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Silero VAD weights � avoids cold-start download on first room join.
RUN python -c "from livekit.plugins import silero; silero.VAD.load()"

COPY worker/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "sam_worker.agent", "start"]
