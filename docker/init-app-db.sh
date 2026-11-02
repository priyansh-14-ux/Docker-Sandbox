#!/usr/bin/env bash
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_user="$MEDICODE_DB_USER" \
    --set=app_password="$MEDICODE_DB_PASSWORD" \
    --set=app_database="$MEDICODE_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_user')
\gexec
SQL
