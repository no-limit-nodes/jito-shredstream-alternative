#!/usr/bin/env python3
"""Compare two shred feeds side by side: which delivers each shred first, and by how much.

Point two providers (or two regions) at two UDP ports on the same host, then run:

    python tools/shred_compare.py --a 0.0.0.0:20000 --b 0.0.0.0:20001 --names old,nln --duration 600

Both sockets are read by one loop on one clock, so the lead times are directly comparable.
"""
from __future__ import annotations

import argparse
import json
import selectors
import socket
import sys
import time

from shredlib import FeedComparator, parse_header

RCVBUF = 64 * 1024 * 1024


def parse_addr(text: str):
    host, _, port = text.rpartition(":")
    return (host or "0.0.0.0", int(port))


def open_socket(addr) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
    except OSError:
        pass
    sock.bind(addr)
    sock.setblocking(False)
    return sock


def print_report(cmp: FeedComparator, elapsed: float, as_json: bool, invalid) -> None:
    rep = cmp.report()
    rep["elapsed_s"] = round(elapsed, 1)
    rep["invalid_packets"] = dict(zip(cmp.names, invalid))
    if as_json:
        print(json.dumps(rep), flush=True)
        return
    a, b = cmp.names
    print(f"\n[{elapsed:7.1f}s] shreds on both feeds: {rep['shared']['shreds_on_both']}")
    print(f"  {'feed':<10}{'packets':>10}{'only here':>11}{'first':>9}{'win %':>8}{'median lead':>13}{'p90 lead':>10}")
    for name in (a, b):
        r = rep[name]
        win = f"{r['win_rate'] * 100:.1f}" if r["win_rate"] is not None else "-"
        med = f"{r['median_lead_ms']} ms" if r["median_lead_ms"] is not None else "-"
        p90 = f"{r['p90_lead_ms']} ms" if r["p90_lead_ms"] is not None else "-"
        print(f"  {name:<10}{r['packets']:>10}{r['only_this_feed']:>11}{r['first_on_shared']:>9}{win:>8}{med:>13}{p90:>10}")
    sys.stdout.flush()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--a", required=True, help="listen address for feed A, e.g. 0.0.0.0:20000")
    p.add_argument("--b", required=True, help="listen address for feed B, e.g. 0.0.0.0:20001")
    p.add_argument("--names", default="A,B", help="labels for the two feeds, e.g. jito,nln")
    p.add_argument("--duration", type=float, default=0, help="seconds to run (0 = until Ctrl-C)")
    p.add_argument("--interval", type=float, default=10, help="seconds between reports")
    p.add_argument("--json", action="store_true", help="print reports as JSON lines")
    args = p.parse_args(argv)

    names = tuple(n.strip() for n in args.names.split(","))
    if len(names) != 2:
        p.error("--names needs exactly two labels")
    cmp = FeedComparator(names)  # type: ignore[arg-type]
    invalid = [0, 0]

    sel = selectors.DefaultSelector()
    for i, addr in enumerate((args.a, args.b)):
        sel.register(open_socket(parse_addr(addr)), selectors.EVENT_READ, i)

    start = time.monotonic()
    next_report = start + args.interval
    print(f"listening: {names[0]}={args.a}  {names[1]}={args.b}", flush=True)
    try:
        while True:
            for key, _ in sel.select(timeout=0.5):
                feed, sock = key.data, key.fileobj
                while True:
                    try:
                        pkt = sock.recv(2048)
                    except BlockingIOError:
                        break
                    now = time.monotonic()
                    hdr = parse_header(pkt)
                    if hdr is None:
                        invalid[feed] += 1
                        continue
                    cmp.observe(feed, hdr.key, now)
            now = time.monotonic()
            if now >= next_report:
                print_report(cmp, now - start, args.json, invalid)
                next_report = now + args.interval
            if args.duration and now - start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
    print_report(cmp, time.monotonic() - start, args.json, invalid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
