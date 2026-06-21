#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${GHCR_OWNER:?GHCR_OWNER is required}"
: "${GHCR_READ_TOKEN:?GHCR_READ_TOKEN is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

compose_file="$DEPLOY_PATH/infra/docker-compose.prod.yml"
env_file="$DEPLOY_PATH/.env"

if [ ! -f "$compose_file" ]; then
  echo "Missing compose file: $compose_file" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  echo "Missing env file: $env_file" >&2
  echo "Create it from env.production.example before running deployment." >&2
  exit 1
fi

echo "$GHCR_READ_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

export GHCR_OWNER IMAGE_TAG
docker compose -f "$compose_file" --env-file "$env_file" config > /tmp/paris-ai-agent.compose.rendered.yml
docker compose -f "$compose_file" --env-file "$env_file" pull
docker compose -f "$compose_file" --env-file "$env_file" up -d --remove-orphans
docker image prune -af --filter "until=168h" || true
