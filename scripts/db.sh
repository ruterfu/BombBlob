#!/usr/bin/env bash
# 本地开发用 PostgreSQL：在项目目录 .pgdata/ 中初始化并启动一个独立实例（不影响系统）。
# 用法: scripts/db.sh start | stop | status | psql
set -euo pipefail
cd "$(dirname "$0")/.."
PGBIN="${PGBIN:-$(dirname "$(command -v pg_ctl 2>/dev/null || echo /opt/homebrew/opt/postgresql@17/bin/pg_ctl)")}"
PGDATA="${PGDATA:-$PWD/.pgdata}"
PGPORT="${PGPORT:-5433}"
DB="${PGDATABASE:-bombblob}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

case "${1:-start}" in
  start)
    if [ ! -f "$PGDATA/PG_VERSION" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U postgres --auth=trust -E UTF8 >/dev/null
      echo "initialized $PGDATA"
    fi
    if ! "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
      "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PGPORT -k /tmp -h 127.0.0.1" -l "$PGDATA/server.log" -w start >/dev/null
    fi
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 \
      || "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U postgres "$DB"
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}_test'" | grep -q 1 \
      || "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U postgres "${DB}_test"
    echo "PostgreSQL running: postgresql://postgres@127.0.0.1:$PGPORT/$DB"
    ;;
  stop) "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop ;;
  status) "$PGBIN/pg_ctl" -D "$PGDATA" status ;;
  psql) exec "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres "$DB" ;;
  *) echo "usage: $0 start|stop|status|psql"; exit 1 ;;
esac
