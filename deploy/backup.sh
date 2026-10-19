#!/usr/bin/env bash
# Backup frio consistente; o destino deve ter cifragem e ACL corporativa.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$root"
destination=""
ack=0
while (($#)); do
  case "$1" in
    --encrypted-destination) destination="${2:?destino ausente}"; shift 2 ;;
    --ack-protected-storage) ack=1; shift ;;
    *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
  esac
done
((ack == 1)) || { echo 'Confirme cifragem/ACL do destino com --ack-protected-storage.' >&2; exit 1; }
[[ -d "$destination" ]] || { echo 'Destino protegido não existe.' >&2; exit 1; }
destination="$(cd -- "$destination" && pwd -P)"
case "$destination/" in "$root/"*) echo 'Backup deve ficar fora do projeto.' >&2; exit 1;; esac
backup="$destination/scribrief-beta-$(date +%Y%m%d-%H%M%S)"
[[ ! -e "$backup" ]] || { echo 'Backup já existe.' >&2; exit 1; }
compose() { docker compose --env-file "$root/deploy/beta.env" -f "$root/compose.beta.yaml" "$@"; }
frontend_stopped=0
jobs_stopped=0
cleanup() {
  local status=$?
  if ((jobs_stopped)); then compose up -d backend worker beat || echo 'Falha ao reiniciar jobs' >&2; fi
  if ((frontend_stopped)); then compose up -d frontend || echo 'Falha ao reiniciar frontend' >&2; fi
  exit "$status"
}
trap cleanup EXIT
compose stop frontend
frontend_stopped=1
active_check='from apps.meetings.models import Meeting,MeetingStatus,ProcessingJob,SpeakerAnalysis; import sys; active=ProcessingJob.objects.filter(status__in=["queued","running"]).exists() or Meeting.objects.filter(status__in=[MeetingStatus.EXTRAINDO_AUDIO,MeetingStatus.TRANSCREVENDO,MeetingStatus.GERANDO_ATA]).exists() or SpeakerAnalysis.objects.filter(status="processing").exists(); sys.exit(3 if active else 0)'
if ! compose exec -T backend python manage.py shell -c "$active_check"; then
  echo 'Há jobs ativos ou a verificação falhou; backup recusado.' >&2
  exit 1
fi
compose stop backend worker beat
jobs_stopped=1
umask 077
mkdir -p -- "$backup/media" "$backup/secrets"
compose exec -T db pg_dump -Fc -U scribrief -d scribrief -f /tmp/scribrief-beta.dump
db_id="$(compose ps -q db)"
worker_id="$(compose ps -q --all worker)"
[[ -n "$db_id" && -n "$worker_id" ]] || { echo 'Banco ou worker ausente.' >&2; exit 1; }
docker cp "$db_id:/tmp/scribrief-beta.dump" "$backup/database.dump"
docker cp "$worker_id:/app/dados/." "$backup/media"
cp -- "$root/deploy/beta.env" "$backup/beta.env"
cp -- "$root"/deploy/secrets/* "$backup/secrets/"
docker run --rm --network none -v "$backup:/backup" -v "$root/deploy:/deploy:ro" \
  python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 python /deploy/manifest.py create /backup
echo "Backup criado em $backup. Contém dados e segredos em claro; proteja-o e teste a restauração."
