#!/usr/bin/env bash
# onedl installer - deploy the burn-after-read download service.
# Run as root on the target host (CentOS 7 + python2.7 in this project).
set -e

BASE="/opt/onedl"
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "==> installing onedl into $BASE"
mkdir -p "$BASE/tokens" "$BASE/consumed" "$BASE/store"
install -m 644 "$SRC/service.py" "$BASE/service.py"
install -m 755 "$SRC/gen.py"     "$BASE/gen.py"

echo "==> installing systemd unit"
install -m 644 "$SRC/onedl.service" /etc/systemd/system/onedl.service
systemctl daemon-reload
systemctl enable onedl
systemctl restart onedl
sleep 2
systemctl is-active onedl && echo "    service: ACTIVE" || echo "    service: NOT RUNNING"

echo
echo "==> nginx config (manual step - read carefully)"
echo "    Drop this block into your nginx server{} (replace 127.0.0.1 with the"
echo "    docker bridge gateway IP if nginx runs in a container):"
echo
sed 's/^/    /' "$SRC/onedl.nginx.conf"
echo
echo "    IMPORTANT (docker bind-mount gotcha): do NOT 'sed -i' a config that is"
echo "    bind-mounted into a container - the running container keeps the OLD"
echo "    inode. Either edit the file in place and send HUP, or 'docker restart"
echo "    <nginx>' so it re-binds the current file. Then:  docker exec nginx nginx -t"
echo
echo "==> usage"
echo "    python $BASE/gen.py <file> [count]   # mint one-time links"
echo "    systemctl status onedl               # service status"
echo "    journalctl -u onedl                  # logs"
echo "    ls $BASE/tokens | wc -l              # live (unspent) links"
echo "    ls $BASE/consumed | wc -l            # already spent links"
