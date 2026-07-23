#!/usr/bin/env bash
# Deploy manual a Railway. El proyecto NO tiene autodeploy desde GitHub:
# un `git push` no despliega nada por si solo, hay que correr este script.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MAX_WAIT_SECONDS=300

echo "==> Deploy manual a Railway (servicio: brain)"
UP_OUTPUT=$(MSYS_NO_PATHCONV=1 railway up -s brain --detach 2>&1)
echo "$UP_OUTPUT"

DEPLOY_ID=$(echo "$UP_OUTPUT" | grep -oE 'id=[a-f0-9-]{36}' | head -1 | cut -d= -f2)
if [ -z "$DEPLOY_ID" ]; then
    echo "==> No pude extraer el ID del deploy nuevo; sigo el mas reciente de la lista"
fi

echo "==> Esperando a que el build termine (maximo ${MAX_WAIT_SECONDS}s)..."
START=$(date +%s)
STATUS_LINE=""
while true; do
    NOW=$(date +%s)
    if [ $((NOW - START)) -gt "$MAX_WAIT_SECONDS" ]; then
        echo "==> Timeout esperando el deploy — revisa 'railway logs -s brain' manualmente"
        exit 1
    fi

    if [ -n "$DEPLOY_ID" ]; then
        LINE=$(MSYS_NO_PATHCONV=1 railway deployment list -s brain 2>&1 | grep "$DEPLOY_ID" || true)
    else
        LINE=$(MSYS_NO_PATHCONV=1 railway deployment list -s brain 2>&1 | sed -n '2p')
    fi

    if echo "$LINE" | grep -qE "SUCCESS|FAILED|CRASHED"; then
        STATUS_LINE="$LINE"
        break
    fi
    sleep 8
done

echo "==> $STATUS_LINE"
if echo "$STATUS_LINE" | grep -q SUCCESS; then
    echo "==> Deploy OK"
    exit 0
else
    echo "==> Deploy FALLO — revisa 'railway logs -s brain'"
    exit 1
fi
