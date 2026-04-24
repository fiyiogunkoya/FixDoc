# Self-contained backend image — build context = `backend/`.
#
# Railway's current UI only lets us set a single Root Directory per service,
# so the backend can't reach `../src/` or `../pyproject.toml` during build.
# Instead we install the `fixdoc` library from the public GitHub repo at a
# pinned ref — same source of truth, no monorepo gymnastics in Docker.
#
# FIXDOC_GIT_REF defaults to `k8s` (current working branch); bump to `main`
# once the SaaS work is merged.

FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev git \
  && rm -rf /var/lib/apt/lists/*

ARG FIXDOC_GIT_REPO=https://github.com/fiyiogunkoya/FixDoc.git
ARG FIXDOC_GIT_REF=k8s

RUN pip install --upgrade pip \
  && pip install --no-cache-dir "fixdoc @ git+${FIXDOC_GIT_REPO}@${FIXDOC_GIT_REF}"

# Install the backend itself — depends on fixdoc, which pip finds in the
# env from the line above (bare `fixdoc` in backend/pyproject.toml resolves
# to the already-installed version).
COPY pyproject.toml /build/
COPY app/ /build/app/
RUN pip install --no-cache-dir /build


FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/* \
  && adduser --system --group --no-create-home fixdoc

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=fixdoc . /app/

USER fixdoc

ENV PORT=8000
EXPOSE 8000

# Alembic runs before uvicorn — atomic rollout per replica. If migration
# fails the container exits non-zero and Railway's healthcheck fails the
# deploy without flipping traffic.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]
