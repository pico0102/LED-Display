#!/usr/bin/env python3
"""tools/test_logic.py - Unit tests for pure logic modules.
Runs on desktop Python (unittest).
Modules tested: time_common, sports_logic, sleeper_logic.
Board-only modules (board, displayio, etc.) must NEVER be imported by these modules.
"""

import os
import sys
import unittest

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Check if modules exist before importing to allow running during earlier phases
try:
    import time_common
except ImportError:
    time_common = None

try:
    import sports_logic
except ImportError:
    sports_logic = None

try:
    import sleeper_logic
except ImportError:
    sleeper_logic = None


class TestPureModulesImport(unittest.TestCase):
    def test_framework_ready(self):
        """Smoke test verifying unittest framework runs."""
        self.assertTrue(True)


@unittest.skipIf(time_common is None, "time_common not implemented yet (Phase 2)")
class TestTimeLogic(unittest.TestCase):
    def test_civil_calendar_roundtrip(self):
        """Test days_from_civil and civil_from_days for various dates."""
        cases = [
            (1970, 1, 1),
            (2000, 2, 29),  # century leap year
            (2024, 2, 29),  # regular leap year
            (2026, 3, 8),
            (2026, 10, 13),
            (2026, 11, 1),
            (2030, 12, 31),
        ]
        for y, m, d in cases:
            days = time_common.days_from_civil(y, m, d)
            y2, m2, d2 = time_common.civil_from_days(days)
            self.assertEqual((y, m, d), (y2, m2, d2), f"Mismatch for {y}-{m}-{d}")

    def test_leap_years(self):
        """Test days count between Feb 28 and Mar 1 on leap and non-leap years."""
        # 2024 is a leap year (Feb 29 exists)
        d_feb28_2024 = time_common.days_from_civil(2024, 2, 28)
        d_feb29_2024 = time_common.days_from_civil(2024, 2, 29)
        d_mar01_2024 = time_common.days_from_civil(2024, 3, 1)
        self.assertEqual(d_feb29_2024 - d_feb28_2024, 1)
        self.assertEqual(d_mar01_2024 - d_feb29_2024, 1)

        # 2025 is not a leap year
        d_feb28_2025 = time_common.days_from_civil(2025, 2, 28)
        d_mar01_2025 = time_common.days_from_civil(2025, 3, 1)
        self.assertEqual(d_mar01_2025 - d_feb28_2025, 1)

    def test_parse_iso_utc_both_shapes(self):
        """Test parse_iso_utc for both short and full ISO formats."""
        ts1 = time_common.parse_iso_utc("2026-10-18T17:00Z")
        ts2 = time_common.parse_iso_utc("2026-10-18T17:00:00Z")
        self.assertEqual(ts1, ts2)

        # 2026-10-13T22:00:00Z
        ts3 = time_common.parse_iso_utc("2026-10-13T22:00:00Z")
        # 2026-10-13 is Tuesday
        self.assertEqual(time_common.weekday(ts3), 1)  # Tuesday = 1

    def test_parse_rfc1123(self):
        """Test parse_rfc1123 for HTTP Date header."""
        ts = time_common.parse_rfc1123("Tue, 13 Oct 2026 22:15:03 GMT")
        ts_iso = time_common.parse_iso_utc("2026-10-13T22:15:03Z")
        self.assertEqual(ts, ts_iso)

    def test_eastern_dst_spring_boundary(self):
        """US DST 2026 starts 2nd Sunday of March (2026-03-08) at 07:00 UTC."""
        ts_before = time_common.parse_iso_utc("2026-03-08T06:59:00Z")
        ts_after = time_common.parse_iso_utc("2026-03-08T07:00:00Z")

        # 06:59Z is still EST (-5 hours = -18000s)
        self.assertEqual(time_common.eastern_offset(ts_before), -18000)
        # 07:00Z transitions to EDT (-4 hours = -14400s)
        self.assertEqual(time_common.eastern_offset(ts_after), -14400)

    def test_eastern_dst_fall_boundary(self):
        """US DST 2026 ends 1st Sunday of November (2026-11-01) at 06:00 UTC."""
        ts_before = time_common.parse_iso_utc("2026-11-01T05:59:00Z")
        ts_after = time_common.parse_iso_utc("2026-11-01T06:00:00Z")

        # 05:59Z is still EDT (-4 hours = -14400s)
        self.assertEqual(time_common.eastern_offset(ts_before), -14400)
        # 06:00Z transitions back to EST (-5 hours = -18000s)
        self.assertEqual(time_common.eastern_offset(ts_after), -18000)

    def test_fmt_game_time(self):
        """Test fmt_game_time for 2026-10-18T17:00Z -> ('SUN', '1:00P', 'OCT 18')."""
        ts = time_common.parse_iso_utc("2026-10-18T17:00Z")
        day_str, time_str, date_str = time_common.fmt_game_time(ts)
        self.assertEqual(day_str, "SUN")
        self.assertEqual(time_str, "1:00P")
        self.assertEqual(date_str, "OCT 18")

    def test_fmt_clock(self):
        """Test fmt_clock for 2026-10-13T22:04:00Z (6:04 PM EDT)."""
        ts = time_common.parse_iso_utc("2026-10-13T22:04:00Z")
        self.assertEqual(time_common.fmt_clock(ts), "6:04P")

        # Morning test: 14:04Z -> 10:04A EDT
        ts_am = time_common.parse_iso_utc("2026-10-13T14:04:00Z")
        self.assertEqual(time_common.fmt_clock(ts_am), "10:04A")



@unittest.skipIf(sports_logic is None, "sports_logic not implemented yet (Phase 4)")
class TestSportsLogic(unittest.TestCase):
    def test_placeholder(self):
        pass


@unittest.skipIf(sleeper_logic is None, "sleeper_logic not implemented yet (Phase 5)")
class TestSleeperLogic(unittest.TestCase):
    def test_placeholder(self):
        pass


if __name__ == "__main__":
    unittest.main()
