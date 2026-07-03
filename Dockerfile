FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends make && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
# DEV=true adds pytest + ruff for the `tests` Compose service.
ARG DEV=false
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

COPY . .

# Offline replay of the committed transcripts is the default. SEED_DIR can point at another seed.
ENV REPLAY_LLM=true \
    SEED_DIR=/app/seed

# Writes /app/out/branded_package.json, audit.json and exception_queue.json, then runs the gate.
CMD ["sh", "-c", "make demo && make verify"]
