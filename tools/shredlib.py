"""Minimal parser for Solana shred packets (the wire format Jito ShredStream forwards).

Only the common header is parsed, which is enough to identify a shred:

    offset  size  field
    0       64    signature
    64      1     shred variant (data / code, legacy / merkle)
    65      8     slot           (u64, little endian)
    73      4     index          (u32)
    77      2     shred version  (u16)
    79      4     fec_set_index  (u32)
    83            end of common header

Standard library only, so it runs anywhere Python 3.9+ runs.
"""
from __future__ import annotations

import struct
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

SIGNATURE_LEN = 64
COMMON_HEADER_LEN = 83

LEGACY_DATA = 0xA5
LEGACY_CODE = 0x5A
MERKLE_CODE_NIBBLES = (0x40, 0x60, 0x70)  # plain, chained, chained + resigned
MERKLE_DATA_NIBBLES = (0x80, 0x90, 0xB0)


@dataclass(frozen=True)
class ShredHeader:
    slot: int
    index: int
    version: int
    fec_set_index: int
    variant: int
    kind: str  # "data" or "code"
    merkle: bool

    @property
    def key(self) -> Tuple[int, str, int]:
        """Identity of a shred across feeds: the same shred has the same key everywhere."""
        return (self.slot, self.kind, self.index)


def classify_variant(byte: int) -> Tuple[Optional[str], bool]:
    """Return (kind, is_merkle) for a shred variant byte, or (None, False) if unknown."""
    if byte == LEGACY_DATA:
        return "data", False
    if byte == LEGACY_CODE:
        return "code", False
    high = byte & 0xF0
    if high in MERKLE_CODE_NIBBLES:
        return "code", True
    if high in MERKLE_DATA_NIBBLES:
        return "data", True
    return None, False


def parse_header(packet: bytes) -> Optional[ShredHeader]:
    """Parse the common shred header. Returns None for packets that are not shreds."""
    if len(packet) < COMMON_HEADER_LEN:
        return None
    variant = packet[SIGNATURE_LEN]
    kind, merkle = classify_variant(variant)
    if kind is None:
        return None
    slot, index, version, fec_set_index = struct.unpack_from("<QIHI", packet, SIGNATURE_LEN + 1)
    return ShredHeader(slot, index, version, fec_set_index, variant, kind, merkle)


def make_test_shred(slot: int, index: int, kind: str = "data", version: int = 50093,
                    fec_set_index: int = 0, size: int = 1228) -> bytes:
    """Build a synthetic packet with a valid common header (for tests and demos only)."""
    variant = 0x96 if kind == "data" else 0x66  # merkle chained data / code
    header = bytes(SIGNATURE_LEN) + bytes([variant]) + struct.pack(
        "<QIHI", slot, index, version, fec_set_index)
    return header + bytes(max(0, size - len(header)))


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[k]


class FeedComparator:
    """Compares two shred feeds by recording which one delivered each shred first.

    A shred is keyed by (slot, kind, index). For every shred seen on both feeds the
    feed that delivered it first gets a "win" and the gap is recorded as its lead.
    """

    def __init__(self, names: Tuple[str, str] = ("A", "B"), max_keys: int = 1_000_000,
                 max_samples: int = 200_000):
        self.names = names
        self.max_keys = max_keys
        self._first: "OrderedDict[tuple, list]" = OrderedDict()
        self.packets = [0, 0]
        self.duplicates = [0, 0]
        self.only = [0, 0]
        self.both = 0
        self.wins = [0, 0]
        self.leads_ms: List[Deque[float]] = [deque(maxlen=max_samples), deque(maxlen=max_samples)]

    def observe(self, feed: int, key: tuple, t: float) -> None:
        """Record that `feed` (0 or 1) delivered shred `key` at monotonic time `t` (seconds)."""
        self.packets[feed] += 1
        entry = self._first.get(key)
        if entry is None:
            self._first[key] = [feed, t, False]
            self.only[feed] += 1
            if len(self._first) > self.max_keys:
                self._first.popitem(last=False)
            return
        first_feed, first_t, matched = entry
        if first_feed == feed or matched:
            self.duplicates[feed] += 1
            return
        entry[2] = True
        self.only[first_feed] -= 1
        self.both += 1
        self.wins[first_feed] += 1
        self.leads_ms[first_feed].append((t - first_t) * 1000.0)

    def report(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for i, name in enumerate(self.names):
            leads = list(self.leads_ms[i])
            out[name] = {
                "packets": self.packets[i],
                "duplicates": self.duplicates[i],
                "only_this_feed": self.only[i],
                "first_on_shared": self.wins[i],
                "win_rate": round(self.wins[i] / self.both, 4) if self.both else None,
                "median_lead_ms": _round(percentile(leads, 50)),
                "p90_lead_ms": _round(percentile(leads, 90)),
            }
        out["shared"] = {"shreds_on_both": self.both}
        return out


def _round(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v, 3)
