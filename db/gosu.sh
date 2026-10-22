#!/bin/sh
set -eu

# Fail closed if upstream entrypoint changes the expected invocation.
[ "${1:-}" = postgres ] || { echo 'Apenas postgres é permitido' >&2; exit 1; }
uid="$(id -u postgres)" || exit 1
[ "$uid" -gt 0 ] || { echo 'UID inválido para postgres' >&2; exit 1; }
exec /sbin/su-exec "$@"
