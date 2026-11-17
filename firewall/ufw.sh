#!/usr/bin/env bash
# Open the shred UDP port with ufw.
# Usage: sudo PORT=20000 ./firewall/ufw.sh
#        sudo PORT=20000 SOURCES="1.2.3.4 5.6.7.8" ./firewall/ufw.sh   # only allow provider IPs
set -euo pipefail
PORT="${PORT:-20000}"
if [[ -n "${SOURCES:-}" ]]; then
  for ip in $SOURCES; do ufw allow proto udp from "$ip" to any port "$PORT" comment "shred feed"; done
else
  ufw allow "$PORT"/udp comment "shred feed"
fi
ufw status | grep "$PORT" || true
