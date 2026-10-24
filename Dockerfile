# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# twc-admin — Django admin panel (manages the shared TheWhiteCode database)
#
# Best practices in play:
# - Multi-stage: gcc only in the builder (argon2-cffi bindings compile),
#   the runtime image stays slim and has no compiler.
# - Non-root user (uid 10001).
# - No secrets baked in: the shared app's config/.env is passed at RUNTIME
#   via compose `env_file`, never COPYed into the image.
# - Healthcheck on the public /login/ endpoint.
# - tini-style init via compose `init: true` (reaps gunicorn children).
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build wheels ────────────────────────────────────────────────────
FROM python:3.14-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --gid 10001 django \
 && useradd --uid 10001 --gid django --create-home django
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels
COPY --chown=django:django . /app
# /app itself stays root-owned after the COPY (chown only covers the
# copied entries) — fix it so collectstatic can create /app/staticfiles.
RUN chmod +x /app/docker-entrypoint.sh  \
 && mkdir -p /data \
 && chown django:django /app /data
USER django
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login/', timeout=4)" || exit 1
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "twc_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
