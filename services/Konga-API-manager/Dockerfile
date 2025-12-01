# Use official Kong base image
FROM kong:3.4

# Copy configuration and helper scripts into the image
COPY kong.yml /kong/kong.yml
COPY --chmod=0755 substitute-env.sh /docker-entrypoint.d/10-substitute-env.sh

# Environment for DB-less and declarative config path
ENV KONG_DATABASE=off \
    KONG_DECLARATIVE_CONFIG=/tmp/kong-substituted.yml \
    KONG_ADMIN_LISTEN=0.0.0.0:8001

# Expose standard Kong ports
EXPOSE 8000 8443 8001 8444

# Default command uses Kong's entrypoint; our script runs via /docker-entrypoint.d
CMD ["/docker-entrypoint.sh", "kong", "docker-start"]


