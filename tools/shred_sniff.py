#!/usr/bin/env python3
"""Verify a new shred feed: packets per second, bandwidth, slots, data/code mix.

    python tools/shred_sniff.py --listen 0.0.0.0:20000
    python tools/shred_sniff.py --listen 0.0.0.0:20000 --rpc https://your-rpc-endpoint

With --rpc it also compares the newest slot seen in shreds with the RPC's
`processed` slot, which shows how far ahead of RPC the shred feed runs.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.request

from shredlib import parse_header

RCVBUF = 64 * 1024 * 1024


def rpc_slot(url: str) -> int | None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getSlot",
                       "params": [{"commitment": "processed"}]}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return int(json.load(r)["result"])
    except Exception:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--listen", default="0.0.0.0:20000", help="UDP address the feed sends to")
    p.add_argument("--interval", type=float, default=5)
    p.add_argument("--duration", type=float, default=0, help="seconds to run (0 = until Ctrl-C)")
    p.add_argument("--rpc", help="optional RPC URL to compare slot height against")
    args = p.parse_args(argv)

    host, _, port = args.listen.rpartition(":")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
    except OSError:
        pass
    sock.bind((host or "0.0.0.0", int(port)))
    sock.settimeout(0.5)
    print(f"listening on {args.listen} (Ctrl-C to stop)", flush=True)

    start = last = time.monotonic()
    pkts = byts = data = code = bad = 0
    slots: set = set()
    max_slot = 0
    total = 0
    try:
        while True:
            try:
                pkt = sock.recv(2048)
                hdr = parse_header(pkt)
                pkts += 1
                byts += len(pkt)
                if hdr is None:
                    bad += 1
                else:
                    slots.add(hdr.slot)
                    max_slot = max(max_slot, hdr.slot)
                    if hdr.kind == "data":
                        data += 1
                    else:
                        code += 1
            except socket.timeout:
                pass
            now = time.monotonic()
            if now - last >= args.interval:
                dt = now - last
                total += pkts
                line = (f"{pkts / dt:8.0f} pkt/s  {byts * 8 / dt / 1e6:7.1f} Mbit/s  "
                        f"data {data}  code {code}  invalid {bad}  slots {len(slots)}  newest {max_slot or '-'}")
                if args.rpc and max_slot:
                    s = rpc_slot(args.rpc)
                    if s is not None:
                        line += f"  rpc {s}  shred lead {max_slot - s:+d} slots"
                print(line, flush=True)
                if pkts == 0 and total == 0:
                    print("  no packets yet: check the destination IP:port, firewall and cloud security group",
                          flush=True)
                pkts = byts = data = code = bad = 0
                slots.clear()
                last = now
            if args.duration and now - start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
