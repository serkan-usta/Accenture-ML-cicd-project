# Stage 1: Builder
# FIX: Multi-stage build keeps dev tools out of the final image
FROM python:3.11.9-slim AS builder
# FIX: Pinned to minor and patch. "3.11-slim" can drift to a different patch.

WORKDIR /build

# FIX: Copy only requirements first, not src
#      If requirements.txt is unchanged, pip layer is served from cache
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11.9-slim AS runtime

# FIX: Build metadata labels record who built the image, when, and from which commit
ARG BUILD_DATE
ARG GIT_SHA
ARG GIT_BRANCH
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.ref.name="${GIT_BRANCH}" \
      org.opencontainers.image.title="ml-model" \
      org.opencontainers.image.vendor="your-org"

WORKDIR /app

# FIX: Non-root user. Running as root is a security risk.
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

# System runtime deps (curl only, gcc stayed in the builder stage)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
# FIX: Added --no-install-recommends to avoid pulling in unnecessary packages

# Copy pip packages from builder
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ ./src/

# FIX: Transfer file ownership to appuser
RUN chown -R appuser:appgroup /app

USER appuser
# FIX: Container no longer runs as root

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# FIX: ENTRYPOINT instead of CMD, cannot be accidentally overridden
ENTRYPOINT ["python", "-m", "src.serve"]
# FIX: Run as a Python module, not a script path
