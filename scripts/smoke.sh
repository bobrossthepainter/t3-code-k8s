#!/usr/bin/env bash
# Test the actual runtime with the chart's restricted security settings.
set -euo pipefail
image=${1:?Usage: scripts/smoke.sh IMAGE}
name="t3-smoke-${RANDOM}-${RANDOM}"
volume="${name}-data"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker volume create "$volume" >/dev/null
# Kubernetes fsGroup handles PVC ownership; initialize a Docker volume equivalently.
docker run --rm --user 0 --entrypoint chown -v "$volume:/data" "$image" 10001:10001 /data
docker run -d --name "$name" --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m -v "$volume:/data" \
  -p 127.0.0.1::3773 "$image" >/dev/null
ready() {
  # Docker can reassign an ephemeral host port when the container restarts.
  local port
  port=$(docker port "$name" 3773/tcp | awk -F: '{print $NF}')
  for _ in $(seq 1 90); do
    if curl --fail --silent --max-time 5 "http://127.0.0.1:$port/" -o /dev/null; then return 0; fi
    sleep 2
  done
  echo 'Server did not become ready (logs may contain pairing secrets; inspect locally).' >&2
  return 1
}
ready
docker exec "$name" sh -ec '
  test "$(id -u)" = 10001
  for cli in codex claude npm; do
    if command -v "$cli"; then exit 1; fi
  done
'
# Pairing must work headlessly, not just static asset serving. Do not print tokens.
docker exec "$name" t3 auth pairing create --json > /dev/null
identity=$(docker exec "$name" sh -c 'cat "$T3CODE_HOME/userdata/environment-id"')
test -n "$identity"
docker restart "$name" >/dev/null
ready
test "$identity" = "$(docker exec "$name" sh -c 'cat "$T3CODE_HOME/userdata/environment-id"')"
docker exec "$name" t3 auth pairing create --json > /dev/null
echo "Runtime smoke test passed: $image"
