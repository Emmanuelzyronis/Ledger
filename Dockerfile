# LEDGER service image (Epic 7 / EMM-83).
#
# Multi-stage: the builder resolves and installs dependencies into a virtual
# environment, the runtime stage copies only that environment and the source.
# The container runs as a non-root user, ships no credentials, and needs a
# writable volume for the single authoritative SQLite database.
#
# Pin the base image by digest before a production release:
#   docker build --build-arg PYTHON_IMAGE=python:3.12.7-slim-bookworm@sha256:<digest> .

ARG PYTHON_IMAGE=python:3.12.7-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt requirements-server.txt ./
# LEDGER has no mandatory runtime dependencies. If requirements.txt ever gains
# one it must be hash-pinned, so this step refuses an unpinned install.
RUN python -m venv /opt/venv \
 && if grep -qvE '^[[:space:]]*(#|$)' requirements.txt; then \
      /opt/venv/bin/pip install --require-hashes -r requirements.txt; \
    fi

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH \
    LEDGER_ENV=production LEDGER_HOST=0.0.0.0 LEDGER_PORT=8080 \
    LEDGER_DATABASE_PATH=/var/lib/ledger/ledger.sqlite3
RUN useradd --system --uid 10001 --home /var/lib/ledger --create-home ledger \
 && mkdir -p /var/lib/ledger /app \
 && chown -R ledger:ledger /var/lib/ledger
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
COPY docs/openapi ./docs/openapi
COPY VERSION ./
USER ledger
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('http://127.0.0.1:8080/v1/health'))['data']['status'])" || exit 1
ENTRYPOINT ["python", "-m", "ledger"]
