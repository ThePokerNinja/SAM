# Samuel LiveKit agent worker (Phase 0 prod).
# Build context: SAM repo root (see render.yaml dockerContext).

FROM python:3.15-slim-bookworm
# Must equal the FROM tag. Printed on the RM_RUNTIME line Sentinel reads.
ENV RM_BASE_IMAGE=python:3.12-slim-bookworm

WORKDIR /app

# ca-certificates is upgraded on every build: the slim tag can predate a CA
# distrust (eMudhra intermediate keys, 2026-10-19).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    && apt-get install -y --only-upgrade --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Silero VAD weights — avoids cold-start download on first room join.
RUN python -c "from livekit.plugins import silero; silero.VAD.load()"

COPY worker/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "sam_worker.agent", "start"]
