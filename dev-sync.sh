#!/usr/bin/env bash
# Sync local timemachine package to the Pi and restart the service.
# Usage:  ./dev-sync.sh [--no-restart]

set -euo pipefail

HOST="deadhead@timemachine.lan"
REMOTE_PKG="/home/deadhead/timemachine/lib/python3.9/site-packages/timemachine/"
LOCAL_PKG="$(cd "$(dirname "$0")" && pwd)/timemachine/"

RESTART=true
for arg in "$@"; do
  [[ "$arg" == "--no-restart" ]] && RESTART=false
done

echo "==> Syncing $LOCAL_PKG → $HOST:$REMOTE_PKG"
rsync -av --progress \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='metadata/' \
  "$LOCAL_PKG" "$HOST:$REMOTE_PKG"

if $RESTART; then
  echo "==> Restarting timemachine.service"
  ssh "$HOST" "sudo systemctl restart timemachine.service"
  echo "==> Done. Tailing logs (Ctrl-C to stop):"
  ssh "$HOST" "journalctl -u timemachine.service -f -n 30"
fi
