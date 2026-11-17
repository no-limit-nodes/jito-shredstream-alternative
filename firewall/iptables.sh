#!/usr/bin/env bash
# Open the shred UDP port with iptables (not persistent: save with iptables-save / netfilter-persistent).
# Usage: sudo PORT=20000 [SOURCES="1.2.3.4 5.6.7.8"] ./firewall/iptables.sh
set -euo pipefail
PORT="${PORT:-20000}"
if [[ -n "${SOURCES:-}" ]]; then
  for ip in $SOURCES; do iptables -I INPUT -p udp -s "$ip" --dport "$PORT" -j ACCEPT; done
else
  iptables -I INPUT -p udp --dport "$PORT" -j ACCEPT
fi
iptables -L INPUT -n | grep "dpt:$PORT" || true
