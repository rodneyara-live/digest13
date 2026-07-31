#!/bin/bash
# Digest 13 — Script de notificación de fallo
# Ejecuta cuando digest13.service falla (via OnFailure= en systemd)
# También puede invocarse manualmente después de un fallo:
#   ./on-failure.sh $?

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/failures.log"

mkdir -p "$LOG_DIR"

EXIT_CODE="${1:-desconocido}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Digest 13 falló (exit code: ${EXIT_CODE})" >> "$LOG_FILE"
