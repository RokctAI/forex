# Copyright (c) 2026 RokctAI
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""Equity, margin level and freshness, pinned standalone (no frappe, no
site — `python -m unittest`).

The boundary these tests exist to hold: **this module never invents a
number.** Every missing or unusable input raises, because the output of this
arithmetic becomes a position size.
"""

import importlib.util
import os
import unittest
from datetime import datetime, timedelta

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "margin.py")
_spec = importlib.util.spec_from_file_location("rforex_margin", _MODULE_PATH)
margin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(margin)

NOW = datetime(2026, 8, 11, 9, 0, 0)

LONG = {"id": "p1", "currency": "USD", "unrealised_pl": 125.50}
SHORT = {"id": "p2", "currency": "USD", "unrealised_pl": -40.25}


class TestCurrencyIsMandatory(unittest.TestCase):
    def test_missing_currency_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.normalise_currency(None)

    def test_blank_currency_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.normalise_currency("   ")

    def test_symbol_is_not_a_currency_code(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.normalise_currency("$")

    def test_code_is_uppercased(self):
        self.assertEqual(margin.normalise_currency("usd"), "USD")

    def test_mixed_currencies_raise_rather_than_summing(self):
        # The failure that looks like a working dashboard: a JPY P/L summed
        # into a USD equity.
        positions = [LONG, {"id": "p3", "currency": "JPY", "unrealised_pl": 8000}]
        with self.assertRaises(margin.MissingMarketData):
            margin.unrealised_total(positions, "USD")

    def test_position_without_a_currency_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.unrealised_total([{"id": "p9", "unrealised_pl": 10.0}], "USD")


class TestEquity(unittest.TestCase):
    def test_equity_is_balance_plus_unrealised(self):
        self.assertAlmostEqual(margin.equity(10000.0, [LONG, SHORT], "USD"), 10085.25)

    def test_flat_book_equity_equals_balance(self):
        self.assertAlmostEqual(margin.equity(10000.0, [], "USD"), 10000.0)

    def test_missing_balance_raises_even_with_a_flat_book(self):
        # The tempting default (0.0) would report an empty account as real.
        with self.assertRaises(margin.MissingMarketData):
            margin.equity(None, [], "USD")

    def test_unparseable_position_pl_raises_rather_than_being_skipped(self):
        bad = {"id": "p4", "currency": "USD", "unrealised_pl": "n/a"}
        with self.assertRaises(margin.MissingMarketData):
            margin.equity(10000.0, [LONG, bad], "USD")

    def test_null_position_pl_raises(self):
        bad = {"id": "p5", "currency": "USD", "unrealised_pl": None}
        with self.assertRaises(margin.MissingMarketData):
            margin.equity(10000.0, [bad], "USD")

    def test_non_record_position_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.equity(10000.0, ["p6"], "USD")

    def test_infinite_balance_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.equity(float("inf"), [], "USD")

    def test_losses_can_take_equity_below_balance(self):
        heavy = {"id": "p7", "currency": "USD", "unrealised_pl": -9500.0}
        self.assertAlmostEqual(margin.equity(10000.0, [heavy], "USD"), 500.0)


class TestMarginLevel(unittest.TestCase):
    def test_level_is_equity_over_used_margin_as_a_percentage(self):
        self.assertAlmostEqual(margin.margin_level_pct(10000.0, 2000.0), 500.0)

    def test_no_open_margin_is_undefined_not_infinite(self):
        # None, not inf (renders as 'inf') and not 0 (that is the stop-out
        # band — exactly backwards).
        self.assertIsNone(margin.margin_level_pct(10000.0, 0))

    def test_negative_used_margin_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.margin_level_pct(10000.0, -1.0)

    def test_free_margin_may_be_negative(self):
        # Clamping this to zero would hide the margin call.
        self.assertAlmostEqual(margin.free_margin(1000.0, 2500.0), -1500.0)

    def test_missing_used_margin_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.margin_level_pct(10000.0, None)


class TestMarginBands(unittest.TestCase):
    def test_none_is_no_positions(self):
        self.assertEqual(margin.margin_state(None), margin.STATE_NO_POSITIONS)

    def test_comfortable_level_is_healthy(self):
        self.assertEqual(margin.margin_state(500.0), margin.STATE_HEALTHY)

    def test_just_above_warning_is_healthy(self):
        self.assertEqual(margin.margin_state(200.01), margin.STATE_HEALTHY)

    def test_exactly_the_warning_threshold_is_a_warning(self):
        # On a boundary, the pessimistic reading wins.
        self.assertEqual(margin.margin_state(200.0), margin.STATE_WARNING)

    def test_exactly_the_margin_call_threshold_is_a_margin_call(self):
        self.assertEqual(margin.margin_state(100.0), margin.STATE_MARGIN_CALL)

    def test_between_call_and_warning_is_a_warning(self):
        self.assertEqual(margin.margin_state(150.0), margin.STATE_WARNING)

    def test_exactly_the_stop_out_threshold_is_a_stop_out(self):
        self.assertEqual(margin.margin_state(50.0), margin.STATE_STOP_OUT)

    def test_below_stop_out_is_a_stop_out(self):
        self.assertEqual(margin.margin_state(12.5), margin.STATE_STOP_OUT)

    def test_bands_are_ordered_worst_first_across_the_thresholds(self):
        seen = [
            margin.margin_state(level)
            for level in (10.0, 75.0, 150.0, 1000.0)
        ]
        self.assertEqual(
            seen,
            [
                margin.STATE_STOP_OUT,
                margin.STATE_MARGIN_CALL,
                margin.STATE_WARNING,
                margin.STATE_HEALTHY,
            ],
        )


class TestFreshness(unittest.TestCase):
    def test_a_fresh_snapshot_is_not_stale(self):
        self.assertFalse(margin.is_stale(NOW - timedelta(seconds=5), NOW))

    def test_an_old_snapshot_is_stale(self):
        self.assertTrue(margin.is_stale(NOW - timedelta(seconds=90), NOW))

    def test_exactly_max_age_is_not_yet_stale(self):
        self.assertFalse(margin.is_stale(NOW - margin.MAX_SNAPSHOT_AGE, NOW))

    def test_one_second_past_max_age_is_stale(self):
        self.assertTrue(
            margin.is_stale(NOW - margin.MAX_SNAPSHOT_AGE - timedelta(seconds=1), NOW)
        )

    def test_a_missing_timestamp_is_stale(self):
        # An untimed number cannot be presented as live.
        self.assertTrue(margin.is_stale(None, NOW))

    def test_a_future_timestamp_is_stale(self):
        # Clocks disagree; a snapshot we cannot age is one we cannot vouch for.
        self.assertTrue(margin.is_stale(NOW + timedelta(seconds=10), NOW))


class TestSnapshot(unittest.TestCase):
    def test_full_snapshot_carries_currency_freshness_and_every_derived_number(self):
        result = margin.snapshot(
            balance=10000.0,
            used_margin=2000.0,
            positions=[LONG, SHORT],
            account_currency="usd",
            as_of=NOW - timedelta(seconds=2),
            now=NOW,
        )
        self.assertEqual(result["currency"], "USD")
        self.assertAlmostEqual(result["equity"], 10085.25)
        self.assertAlmostEqual(result["free_margin"], 8085.25)
        self.assertAlmostEqual(result["margin_level_pct"], 504.2625)
        self.assertEqual(result["margin_state"], margin.STATE_HEALTHY)
        self.assertEqual(result["open_position_count"], 2)
        self.assertFalse(result["stale"])
        self.assertIsNotNone(result["as_of"])

    def test_snapshot_without_a_currency_raises(self):
        with self.assertRaises(margin.MissingMarketData):
            margin.snapshot(
                balance=10000.0,
                used_margin=0.0,
                positions=[],
                account_currency=None,
                as_of=NOW,
                now=NOW,
            )

    def test_a_stale_snapshot_is_labelled_not_suppressed(self):
        result = margin.snapshot(
            balance=10000.0,
            used_margin=0.0,
            positions=[],
            account_currency="USD",
            as_of=NOW - timedelta(minutes=5),
            now=NOW,
        )
        self.assertTrue(result["stale"])
        self.assertIsNone(result["margin_level_pct"])
        self.assertEqual(result["margin_state"], margin.STATE_NO_POSITIONS)

    def test_a_snapshot_with_one_bad_position_raises_rather_than_partially_succeeding(self):
        bad = {"id": "p8", "currency": "USD", "unrealised_pl": None}
        with self.assertRaises(margin.MissingMarketData):
            margin.snapshot(
                balance=10000.0,
                used_margin=2000.0,
                positions=[LONG, bad],
                account_currency="USD",
                as_of=NOW,
                now=NOW,
            )

    def test_a_margin_call_snapshot_reports_the_band_and_a_negative_free_margin(self):
        drowning = {"id": "p10", "currency": "USD", "unrealised_pl": -8200.0}
        result = margin.snapshot(
            balance=10000.0,
            used_margin=2000.0,
            positions=[drowning],
            account_currency="USD",
            as_of=NOW,
            now=NOW,
        )
        self.assertAlmostEqual(result["equity"], 1800.0)
        self.assertAlmostEqual(result["margin_level_pct"], 90.0)
        self.assertEqual(result["margin_state"], margin.STATE_MARGIN_CALL)
        self.assertAlmostEqual(result["free_margin"], -200.0)


if __name__ == "__main__":
    unittest.main()
