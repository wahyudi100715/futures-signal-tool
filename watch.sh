#!/data/data/com.termux/files/usr/bin/bash
# Scan ulang tiap 15 menit. Stop: CTRL+C
set -e
cd "$(dirname "$0")"
INTERVAL="${1:-900}"
echo "Watch mode: scan setiap ${INTERVAL} detik. CTRL+C untuk berhenti."
while true; do
  clear
  echo "=== $(date) ==="
  ./run.sh
  echo
  echo "Tidur ${INTERVAL} detik..."
  sleep "$INTERVAL"
done
