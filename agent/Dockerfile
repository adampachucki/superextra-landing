# superextra-worker — Cloud Run image for the async ADK pipeline worker.
#
# Build context is `agent/` (gcloud run deploy --source=agent sets this).
# Entrypoint: uvicorn serves worker_main:app on $PORT (Cloud Run injects 8080
# by default; the worker_main module listens on whatever $PORT is).
#
# Dependencies are the minimum the worker imports: ADK + FastAPI + uvicorn
# + firestore client. No firebase-admin (Admin SDK pattern is native via
# google-cloud-firestore) and no google-cloud-tasks (the worker receives
# tasks; enqueuing lives in the Node Cloud Function).

FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal. ca-certificates for outbound HTTPS; no build
# toolchain (all pip installs use pre-built wheels on linux/amd64).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so the layer cache survives app-code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY superextra_agent ./superextra_agent
COPY worker_main.py .

# Unbuffered stdout/stderr so Cloud Run logs stream in real time.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Cloud Run injects PORT=8080. Stay inside the container's request timeout
# minus a safety margin: Cloud Run kills worker requests at --timeout=1790s,
# which is still comfortably under Cloud Tasks' 1800s dispatch deadline.
EXPOSE 8080

CMD ["sh", "-c", "uvicorn worker_main:app --host 0.0.0.0 --port ${PORT:-8080}"]
