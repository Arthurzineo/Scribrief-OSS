#!/bin/sh
# Do not log PEM data. nginx reload is graceful and keeps the old config if invalid.
set -eu
path=/etc/nginx/certs/current.pem
last="$(sha256sum "$path" | cut -d' ' -f1)"
while sleep 5; do
  now="$(sha256sum "$path" 2>/dev/null | cut -d' ' -f1 || true)"
  if [ -n "$now" ] && [ "$now" != "$last" ]; then
    if nginx -t >/dev/null 2>&1 && nginx -s reload >/dev/null 2>&1; then
      last="$now"
      echo 'Certificado TLS recarregado.'
    else
      echo 'Falha ao recarregar TLS; configuração anterior mantida.' >&2
    fi
  fi
done
