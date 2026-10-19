#!/usr/bin/env bash
# Instalação beta em Linux com Docker Engine + Compose plugin.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$root"
env_file="$root/deploy/beta.env"
compose_file="$root/compose.beta.yaml"
secret_dir="$root/deploy/secrets"
cert_dir="$root/deploy/certs"
certificate=""
private_key=""
legacy_import=0
skip_admin=0

while (($#)); do
  case "$1" in
    --certificate) certificate="${2:?caminho do certificado ausente}"; shift 2 ;;
    --private-key) private_key="${2:?caminho da chave ausente}"; shift 2 ;;
    --skip-admin) skip_admin=1; shift ;;
    *) printf 'Opção desconhecida: %s\n' "$1" >&2; exit 2 ;;
  esac
done
command -v docker >/dev/null || { echo 'Docker não encontrado' >&2; exit 1; }
docker info --format '{{.ServerVersion}}' >/dev/null || { echo 'Docker daemon indisponível' >&2; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose plugin indisponível' >&2; exit 1; }
if [[ ! -f "$env_file" ]]; then
  cp -- "$root/deploy/beta.env.example" "$env_file"
  echo "Configuração criada em $env_file; ajuste PUBLIC_BIND_IP/PUBLIC_HOSTNAME para a LAN."
fi
umask 077
mkdir -p -- "$secret_dir" "$cert_dir"
chmod 0700 -- "$secret_dir" "$cert_dir"
new_secret() {
  local name="$1" size="$2" padded="$3" value
  if [[ -e "$secret_dir/$name" ]]; then
    [[ -s "$secret_dir/$name" ]] || { echo "Segredo existente vazio: $name" >&2; exit 1; }
    return
  fi
  value="$(docker run --rm --network none python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 python -c "import base64,secrets; x=base64.urlsafe_b64encode(secrets.token_bytes($size)).decode(); print(x if $padded else x.rstrip('='))")"
  [[ ${#value} -ge 20 ]] || { echo "Falha ao gerar $name" >&2; exit 1; }
  printf '%s' "$value" > "$secret_dir/$name"
}
new_secret django_secret 48 False
new_secret database_password 48 False
new_secret redis_password 48 False
new_secret sector_key 32 True
for name in django_secret database_password redis_password sector_key; do
  [[ -f "$secret_dir/$name" && ! -L "$secret_dir/$name" ]] || {
    echo "Segredo inválido ou link simbólico: $name" >&2; exit 1;
  }
done
if [[ -z "$certificate" && -z "$private_key" && -f "$cert_dir/localhost.crt" && -f "$cert_dir/localhost.key" ]]; then
  # One-time import for installations made before the dedicated TLS volume.
  certificate="$cert_dir/localhost.crt"; private_key="$cert_dir/localhost.key"
  legacy_import=1
fi
if [[ -n "$certificate" || -n "$private_key" ]]; then
  [[ -f "$certificate" && -f "$private_key" && ! -L "$certificate" && ! -L "$private_key" ]] || { echo 'Informe certificado e chave TLS regulares e existentes.' >&2; exit 1; }
  certificate="$(realpath -- "$certificate")"; private_key="$(realpath -- "$private_key")"
fi
docker run --rm --network none -v "$root/deploy:/deploy:ro" python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 python /deploy/check_tls.py /deploy --config-only
# Local Compose binds keep host mode. Non-root app/Nginx must read the mounted
# files; the 0700 parent directories deny access to other host users.
chmod 0644 -- "$secret_dir"/{django_secret,database_password,redis_password,sector_key}
compose() { docker compose --env-file "$env_file" -f "$compose_file" "$@"; }
compose config --quiet
compose build backend
tls_args=()
bootstrap_args=()
if [[ -n "$certificate" ]]; then
  tls_args=(-v "$certificate:/source/certificate:ro" -v "$private_key:/source/private-key:ro")
  bootstrap_args=(--certificate /source/certificate --private-key /source/private-key)
fi
if ((legacy_import)); then bootstrap_args+=(--preserve-existing); fi
compose run --rm --no-deps --user root --cap-add CHOWN --cap-add FOWNER \
  --cap-add DAC_OVERRIDE "${tls_args[@]}" backend python -m apps.admin_panel.tls_bootstrap "${bootstrap_args[@]}"
compose up -d --build db redis backend
compose exec -T backend python manage.py migrate --noinput
compose exec -T backend python manage.py check
admin_args=()
if ((skip_admin)); then admin_args=(--skip-create); fi
compose exec -T backend python manage.py bootstrap_admin "${admin_args[@]}"
compose up -d --build worker beat frontend
compose ps
echo 'Instalação beta concluída. Na instalação nova, entre localmente como ADMIN e troque ADMIN123 imediatamente; nenhum demo é criado. Teste TLS, firewall e backup/restore antes de dados reais.'
