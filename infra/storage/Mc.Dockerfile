# Project packaging of the unmodified signed vendor binary; not an official MinIO image.
FROM curlimages/curl@sha256:a2e4c1ef9b660f8ca90b2b725768e0ceade4fc1e52b5859a8d3e6c93db2dc47c
ARG SOURCE_SHA
USER 0:0
WORKDIR /
COPY --chmod=0755 mc /usr/local/bin/mc
COPY --chmod=0644 LICENSE CREDITS source.tar.gz binary.minisig NOTICE inputs.lock.json /usr/share/licenses/asm-mc/
ENV MC_CONFIG_DIR=/tmp/mc
LABEL org.opencontainers.image.source="https://github.com/Elefesys/ai-service-manager" \
      org.opencontainers.image.revision="${SOURCE_SHA}" \
      org.opencontainers.image.title="AI Service Manager mc packaging" \
      org.opencontainers.image.version="RELEASE.2025-02-15T10-36-16Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/mc"]
CMD ["--help"]
