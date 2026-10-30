# syntax=docker/dockerfile:1.7
# Renovate keeps this multi-architecture base digest current.
ARG BASE_IMAGE=ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
FROM ${BASE_IMAGE} AS download
ARG TARGETARCH
ARG T3_VERSION
ARG T3_SHA256_AMD64
ARG T3_SHA256_ARM64
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) arch=x64; checksum="$T3_SHA256_AMD64" ;; \
      arm64) arch=arm64; checksum="$T3_SHA256_ARM64" ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    test -n "$T3_VERSION"; \
    printf '%s' "$checksum" | grep -Eq '^[a-f0-9]{64}$'; \
    curl --fail --location --retry 5 --proto '=https' --tlsv1.2 \
      "https://github.com/pingdotgg/t3code/releases/download/v${T3_VERSION}/t3-${T3_VERSION}-linux-${arch}.tar.gz" \
      --output /tmp/t3.tar.gz; \
    printf '%s  /tmp/t3.tar.gz\n' "$checksum" | sha256sum --check --strict; \
    mkdir /opt-t3; \
    tar -xzf /tmp/t3.tar.gz --strip-components=1 -C /opt-t3; \
    test -x /opt-t3/t3

FROM ${BASE_IMAGE} AS runtime
ARG T3_VERSION
LABEL org.opencontainers.image.title="T3 Code headless server" \
      org.opencontainers.image.description="Server-only packaging; no provider CLIs or agent development toolchain" \
      org.opencontainers.image.version="${T3_VERSION}" \
      org.opencontainers.image.licenses="MIT" \
      io.t3code.upstream="https://github.com/pingdotgg/t3code"
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl libatomic1 libstdc++6 tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 t3 \
    && useradd --uid 10001 --gid 10001 --home-dir /data --no-create-home --shell /bin/bash t3 \
    && mkdir /data && chown 10001:10001 /data
COPY --from=download /opt-t3 /opt/t3
COPY LICENSE /usr/share/licenses/t3-code-k8s/LICENSE
COPY licenses/t3code-MIT.txt /usr/share/licenses/t3code/LICENSE
RUN ln -s /opt/t3/t3 /usr/local/bin/t3
ENV HOME=/data \
    T3CODE_HOME=/data/.t3 \
    T3CODE_HOST=0.0.0.0 \
    T3CODE_PORT=3773 \
    T3CODE_NO_BROWSER=true \
    T3CODE_AUTO_BOOTSTRAP_PROJECT_FROM_CWD=false \
    T3CODE_TELEMETRY_ENABLED=false
USER 10001:10001
WORKDIR /data
EXPOSE 3773
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl --fail --silent --output /dev/null "http://127.0.0.1:${T3CODE_PORT}/" || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/t3/t3"]
CMD ["serve"]
