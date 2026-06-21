#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${GHCR_OWNER:?GHCR_OWNER is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

compose_file="$DEPLOY_PATH/infra/docker-compose.prod.yml"
env_file="$DEPLOY_PATH/.env"
registry_token="${GHCR_READ_TOKEN:-${GHCR_TOKEN:-}}"

: "${registry_token:?GHCR_READ_TOKEN or GHCR_TOKEN is required}"

if [ ! -f "$compose_file" ]; then
  echo "Missing compose file: $compose_file" >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  echo "Missing env file: $env_file" >&2
  echo "Create it from env.production.example before running deployment." >&2
  exit 1
fi

echo "$registry_token" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin

export GHCR_OWNER IMAGE_TAG
docker compose -f "$compose_file" --env-file "$env_file" config > /tmp/paris-ai-agent.compose.rendered.yml
docker compose -f "$compose_file" --env-file "$env_file" pull
docker compose -f "$compose_file" --env-file "$env_file" up -d --remove-orphans

mongo_ready=0
for attempt in $(seq 1 24); do
  if docker compose -f "$compose_file" --env-file "$env_file" exec -T mongo mongosh --quiet --eval "db.adminCommand({ ping: 1 })" >/tmp/paris-ai-agent.mongo-health.json 2>/dev/null; then
    cat /tmp/paris-ai-agent.mongo-health.json
    mongo_ready=1
    break
  fi
  sleep 5
done

if [ "$mongo_ready" -ne 1 ]; then
  echo "MongoDB did not become ready in time." >&2
  docker compose -f "$compose_file" --env-file "$env_file" logs mongo
  exit 1
fi

backend_ready=0
for attempt in $(seq 1 24); do
  if health_json="$(curl -fsS http://127.0.0.1/health 2>/dev/null)"; then
    printf '%s\n' "$health_json"
    if printf '%s' "$health_json" | grep -q '"available":true'; then
      backend_ready=1
      break
    fi
  fi
  sleep 5
done

if [ "$backend_ready" -ne 1 ]; then
  echo "Backend health did not report a connected database in time." >&2
  docker compose -f "$compose_file" --env-file "$env_file" logs backend frontend mongo
  exit 1
fi

curl -fsS http://127.0.0.1/ >/tmp/paris-ai-agent.frontend.html
head -n 20 /tmp/paris-ai-agent.frontend.html
docker compose -f "$compose_file" --env-file "$env_file" ps

docker image prune -af --filter "until=168h" || true
