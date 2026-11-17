import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from shredlib import (FeedComparator, classify_variant, make_test_shred,  # noqa: E402
                      parse_header, percentile)


class VariantTest(unittest.TestCase):
    def test_legacy(self):
        self.assertEqual(classify_variant(0xA5), ("data", False))
        self.assertEqual(classify_variant(0x5A), ("code", False))

    def test_merkle(self):
        for b in (0x46, 0x66, 0x76):
            self.assertEqual(classify_variant(b), ("code", True))
        for b in (0x86, 0x96, 0xB6):
            self.assertEqual(classify_variant(b), ("data", True))

    def test_unknown(self):
        for b in (0x00, 0x12, 0xFF, 0xC0):
            self.assertEqual(classify_variant(b), (None, False))


class ParseTest(unittest.TestCase):
    def test_round_trip(self):
        pkt = make_test_shred(380_123_456, 77, "code", version=50093, fec_set_index=64)
        h = parse_header(pkt)
        self.assertEqual((h.slot, h.index, h.version, h.fec_set_index), (380_123_456, 77, 50093, 64))
        self.assertEqual(h.kind, "code")
        self.assertTrue(h.merkle)
        self.assertEqual(h.key, (380_123_456, "code", 77))

    def test_little_endian_offsets(self):
        pkt = bytearray(100)
        pkt[64] = 0xA5
        struct.pack_into("<Q", pkt, 65, 1)
        struct.pack_into("<I", pkt, 73, 2)
        h = parse_header(bytes(pkt))
        self.assertEqual((h.slot, h.index, h.kind, h.merkle), (1, 2, "data", False))

    def test_rejects_short_and_unknown(self):
        self.assertIsNone(parse_header(b"\x00" * 82))
        self.assertIsNone(parse_header(b"\x00" * 1228))  # variant byte 0x00


class ComparatorTest(unittest.TestCase):
    def test_wins_leads_and_only(self):
        c = FeedComparator(("old", "nln"))
        c.observe(1, (1, "data", 0), 10.000)   # nln first
        c.observe(0, (1, "data", 0), 10.004)
        c.observe(0, (1, "data", 1), 11.000)   # old first
        c.observe(1, (1, "data", 1), 11.001)
        c.observe(1, (1, "data", 2), 12.000)   # nln only
        r = c.report()
        self.assertEqual(r["shared"]["shreds_on_both"], 2)
        self.assertEqual(r["nln"]["first_on_shared"], 1)
        self.assertEqual(r["old"]["first_on_shared"], 1)
        self.assertAlmostEqual(r["nln"]["median_lead_ms"], 4.0, places=2)
        self.assertAlmostEqual(r["old"]["median_lead_ms"], 1.0, places=2)
        self.assertEqual(r["nln"]["only_this_feed"], 1)
        self.assertEqual(r["old"]["only_this_feed"], 0)
        self.assertEqual(r["nln"]["win_rate"], 0.5)

    def test_duplicates_do_not_count_as_wins(self):
        c = FeedComparator()
        k = (5, "code", 3)
        c.observe(0, k, 1.0)
        c.observe(0, k, 1.1)   # same feed again
        c.observe(1, k, 1.2)
        c.observe(1, k, 1.3)   # already matched
        r = c.report()
        self.assertEqual(r["A"]["duplicates"], 1)
        self.assertEqual(r["B"]["duplicates"], 1)
        self.assertEqual(r["shared"]["shreds_on_both"], 1)
        self.assertEqual(r["A"]["packets"], 2)

    def test_eviction_bounds_memory(self):
        c = FeedComparator(max_keys=10)
        for i in range(50):
            c.observe(0, (i, "data", 0), float(i))
        self.assertEqual(len(c._first), 10)

    def test_percentile(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(percentile([3, 1, 2], 50), 2)


if __name__ == "__main__":
    unittest.main()
