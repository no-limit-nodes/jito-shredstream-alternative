#!/usr/bin/env python3
"""Send synthetic shreds to two local ports so you can try shred_compare.py without real feeds.

    python tools/shred_compare.py --a 127.0.0.1:21000 --b 127.0.0.1:21001 --names slow,fast --duration 12 &
    python tools/fake_feeds.py --a 127.0.0.1:21000 --b 127.0.0.1:21001 --b-lead-ms 3 --a-loss 0.02

Feed B gets each shred `--b-lead-ms` earlier than feed A. Packets are fake: only the
common header is valid, so they are useless for anything except testing tools.
"""
from __future__ import annotations

import argparse
import random
import socket
import sys
import time

from shredlib import make_test_shred


def addr(text: str):
    h, _, p = text.rpartition(":")
    return (h, int(p))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--slots", type=int, default=20)
    p.add_argument("--shreds-per-slot", type=int, default=200)
    p.add_argument("--b-lead-ms", type=float, default=2.0)
    p.add_argument("--a-loss", type=float, default=0.0, help="fraction of shreds feed A drops")
    p.add_argument("--b-loss", type=float, default=0.0, help="fraction of shreds feed B drops")
    args = p.parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    a, b = addr(args.a), addr(args.b)
    rng = random.Random(7)
    start_slot = 380_000_000
    for s in range(start_slot, start_slot + args.slots):
        for i in range(args.shreds_per_slot):
            pkt = make_test_shred(s, i, "data" if i % 3 else "code")
            if rng.random() >= args.b_loss:
                sock.sendto(pkt, b)
            time.sleep(args.b_lead_ms / 1000)
            if rng.random() >= args.a_loss:
                sock.sendto(pkt, a)
    print(f"sent {args.slots * args.shreds_per_slot} shreds per feed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
