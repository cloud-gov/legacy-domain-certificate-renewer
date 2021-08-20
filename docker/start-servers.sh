#!/usr/bin/env bash

set -euo pipefail

LOGS=${TMPDIR:-/app/logs}

if ! pgrep -x postgres > /dev/null; then
  echo "Starting Postgresql"
  (
    cd "$PGDATA"
    echo > "$LOGS/postgres.log"
    pg_ctl -l "$LOGS/postgres.log" start 
    psql -h localhost --dbname="local-development-cdn" -f /app/docker/cdn-broker-schema.sql
    psql -h localhost --dbname="local-development-domain" -f /app/docker/domain-broker-schema.sql
  )
fi

if ! pgrep -x pebble > /dev/null; then
  echo "Starting Pebble"
  (
    cd /
    PEBBLE_WFE_NONCEREJECT=0 pebble \
      -config="/test/config/pebble-config.json" \
      -dnsserver="127.0.0.1:8053" \
      -strict \
      > "$LOGS/pebble.log" 2>&1 &
  )
fi
