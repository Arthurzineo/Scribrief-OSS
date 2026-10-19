#!/usr/bin/env bash
# Restaura backup em projeto Compose separado sem publicar portas.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$root"
[[ $# -eq 1 && -d "$1" ]] || { echo 'Uso: restore-test.sh /caminho/do/backup' >&2; exit 2; }
backup="$(cd -- "$1" && pwd -P)"
docker run --rm --network none -v "$backup:/backup:ro" -v "$root/deploy:/deploy:ro" \
  python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 python /deploy/manifest.py verify /backup
project='scribrief-restore-check'
compose_base=(docker compose -p "$project" --env-file "$backup/beta.env" -f "$root/compose.beta.yaml")
[[ -z "$("${compose_base[@]}" ps -q --all db)" ]] || { echo 'Clone de restauração já existe; não sobrescrever.' >&2; exit 1; }
mkdir -p -- "$root/release-out"
overlay="$root/release-out/restore-check-secrets.yaml"
[[ ! -e "$overlay" ]] || { echo 'Overlay de restauração já existe; não sobrescrever.' >&2; exit 1; }
cat > "$overlay" <<EOF
secrets:
  django_secret: {file: '$backup/secrets/django_secret'}
  database_password: {file: '$backup/secrets/database_password'}
  redis_password: {file: '$backup/secrets/redis_password'}
  sector_key: {file: '$backup/secrets/sector_key'}
EOF
compose() { "${compose_base[@]}" -f "$overlay" "$@"; }
compose config --quiet
compose up -d --wait db redis
db_id="$(compose ps -q db)"
docker cp "$backup/database.dump" "$db_id:/tmp/restore.dump"
compose exec -T db pg_restore --no-owner --clean --if-exists -U scribrief -d scribrief /tmp/restore.dump
compose run --no-deps --rm -v "$backup/media:/backup-media:ro" backend sh -c 'cp -R /backup-media/. /app/dados/'
compose run --no-deps --rm -v "$backup:/backup:ro" -v "$root/deploy:/deploy:ro" \
  backend python /deploy/check_restored_media.py /backup/manifest.json /app/dados
compose up -d backend
compose exec -T backend python manage.py check
compose exec -T backend python manage.py migrate --check --noinput
echo "Restauração verificada no projeto isolado $project; nenhuma porta publicada."
