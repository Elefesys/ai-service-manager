# Project packaging of the unmodified signed vendor binary; not an official MinIO image.
# The sole base is the locked linux/amd64 curl 8.19.0 image (curl, CA, busybox shell).
FROM curlimages/curl@sha256:a2e4c1ef9b660f8ca90b2b725768e0ceade4fc1e52b5859a8d3e6c93db2dc47c
ARG SOURCE_SHA
# Preserve the original image UID for existing root-owned LOCAL/TEST /data volumes.
USER 0:0
WORKDIR /
COPY --chmod=0755 minio /usr/local/bin/minio
COPY --chmod=0644 LICENSE CREDITS source.tar.gz binary.minisig NOTICE inputs.lock.json /usr/share/licenses/asm-minio/
LABEL org.opencontainers.image.source="https://github.com/Elefesys/ai-service-manager" \
      org.opencontainers.image.revision="${SOURCE_SHA}" \
      org.opencontainers.image.title="AI Service Manager MinIO packaging" \
      org.opencontainers.image.version="RELEASE.2025-09-07T16-13-09Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
EXPOSE 9000 9001
VOLUME ["/data"]
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data"]
