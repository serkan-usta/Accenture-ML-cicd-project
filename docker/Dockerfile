# ─────────────────────────────────────────
# Stage 1: Builder
# FIX: Multi-stage build — final image'a dev tools gitmiyor
#      Builder'da derleme, final'da sadece runtime
# ─────────────────────────────────────────
FROM python:3.11.9-slim AS builder
# FIX: "slim" değil minor+patch pinned — "3.11-slim" farklı patch'e kayabilir

WORKDIR /build

# FIX: Önce sadece requirements kopyala, src değil
#      requirements.txt değişmezse pip katmanı cache'den gelir
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────
# Stage 2: Final runtime image
# ─────────────────────────────────────────
FROM python:3.11.9-slim AS runtime

# FIX: Build metadata label'ları — image kim tarafından ne zaman build edildi
ARG BUILD_DATE
ARG GIT_SHA
ARG GIT_BRANCH
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.ref.name="${GIT_BRANCH}" \
      org.opencontainers.image.title="ml-model" \
      org.opencontainers.image.vendor="your-org"

WORKDIR /app

# FIX: Non-root user — root ile çalışmak güvenlik riski
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

# System runtime deps (sadece curl — gcc builder'da kaldı)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
# FIX: --no-install-recommends eklendi — gereksiz paket gelmiyor

# Builder'dan pip paketlerini kopyala
COPY --from=builder /install /usr/local

# Kaynak kodunu kopyala
COPY src/ ./src/

# FIX: Dosya sahipliğini appuser'a ver
RUN chown -R appuser:appgroup /app

USER appuser
# FIX: Artık root değil

# SageMaker port 8080'i bekliyor
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# FIX: CMD yerine ENTRYPOINT — override edilemez, daha güvenli
ENTRYPOINT ["python", "-m", "src.serve"]
# FIX: "python src/serve.py" değil — Python module olarak çalıştır