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

"""Forex subscription entitlement rules, pinned standalone (no frappe, no
site — `python -m unittest`).

The boundaries these tests exist to hold: **running is gated on an active
subscription today**, **a tier shortfall is a different answer from no
subscription**, and **an unrecognised tier grants nothing.**
"""

import importlib.util
import os
import unittest
from datetime import date

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "entitlements.py")
_spec = importlib.util.spec_from_file_location("rforex_entitlements", _MODULE_PATH)
entitlements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entitlements)

TODAY = date(2026, 8, 11)

LAPSED = (date(2025, 1, 15), date(2025, 12, 15), "standard")
CURRENT_STANDARD = (date(2026, 6, 1), None, "standard")
CURRENT_PRO = (date(2026, 7, 1), None, "pro")


class TestTierRank(unittest.TestCase):
    def test_ranks_are_ordered(self):
        self.assertLess(
            entitlements.tier_rank("standard"), entitlements.tier_rank("pro")
        )

    def test_an_unknown_tier_ranks_no_better_than_nothing(self):
        self.assertEqual(entitlements.tier_rank("platinum"), 0)
        self.assertEqual(entitlements.tier_rank(None), 0)
        self.assertEqual(entitlements.tier_rank(""), 0)

    def test_tier_names_are_case_insensitive(self):
        self.assertEqual(entitlements.tier_rank("PRO"), entitlements.tier_rank("pro"))


class TestActivity(unittest.TestCase):
    def test_an_open_period_covers_today(self):
        self.assertTrue(entitlements.subscription_active([CURRENT_STANDARD], TODAY))

    def test_a_closed_past_period_does_not(self):
        self.assertFalse(entitlements.subscription_active([LAPSED], TODAY))

    def test_never_subscribed_is_not_active(self):
        self.assertFalse(entitlements.subscription_active([], TODAY))
        self.assertFalse(entitlements.subscription_active(None, TODAY))

    def test_a_day_inside_a_closed_period_is_covered(self):
        self.assertTrue(entitlements.active_on([LAPSED], date(2025, 6, 1)))

    def test_the_boundary_days_are_inclusive(self):
        self.assertTrue(entitlements.active_on([LAPSED], date(2025, 1, 15)))
        self.assertTrue(entitlements.active_on([LAPSED], date(2025, 12, 15)))
        self.assertFalse(entitlements.active_on([LAPSED], date(2025, 1, 14)))
        self.assertFalse(entitlements.active_on([LAPSED], date(2025, 12, 16)))

    def test_a_gap_between_periods_is_not_covered(self):
        self.assertFalse(
            entitlements.active_on([LAPSED, CURRENT_STANDARD], date(2026, 3, 1))
        )


class TestTierResolution(unittest.TestCase):
    def test_the_highest_covering_tier_wins_on_overlap(self):
        # Two live periods, one standard and one pro: they paid for pro.
        self.assertEqual(
            entitlements.highest_tier_on([CURRENT_STANDARD, CURRENT_PRO], TODAY), "pro"
        )

    def test_a_lapsed_pro_period_does_not_raise_todays_tier(self):
        lapsed_pro = (date(2025, 1, 1), date(2025, 2, 1), "pro")
        self.assertEqual(
            entitlements.highest_tier_on([lapsed_pro, CURRENT_STANDARD], TODAY), "standard"
        )

    def test_no_coverage_resolves_to_none(self):
        self.assertEqual(entitlements.highest_tier_on([LAPSED], TODAY), "none")

    def test_a_corrupt_tier_string_does_not_outrank_pro(self):
        junk = (date(2026, 1, 1), None, "zzz_ultimate")
        self.assertEqual(entitlements.highest_tier_on([junk], TODAY), "none")


class TestStrategyVerdict(unittest.TestCase):
    def test_an_active_standard_subscriber_may_run_a_standard_strategy(self):
        self.assertEqual(
            entitlements.strategy_verdict([CURRENT_STANDARD], TODAY, "standard"),
            entitlements.ALLOWED,
        )

    def test_a_lapsed_subscriber_needs_to_reactivate(self):
        self.assertEqual(
            entitlements.strategy_verdict([LAPSED], TODAY, "standard"),
            entitlements.NEEDS_ACTIVE,
        )

    def test_never_subscribed_needs_active(self):
        self.assertEqual(
            entitlements.strategy_verdict([], TODAY, "standard"),
            entitlements.NEEDS_ACTIVE,
        )

    def test_a_standard_subscriber_on_a_pro_strategy_needs_an_upgrade_not_a_subscription(self):
        # Telling somebody who already pays to "subscribe" is the bug this
        # third verdict exists to prevent.
        self.assertEqual(
            entitlements.strategy_verdict([CURRENT_STANDARD], TODAY, "pro"),
            entitlements.NEEDS_UPGRADE,
        )

    def test_a_pro_subscriber_may_run_a_standard_strategy(self):
        self.assertEqual(
            entitlements.strategy_verdict([CURRENT_PRO], TODAY, "standard"),
            entitlements.ALLOWED,
        )

    def test_a_strategy_with_no_declared_tier_still_requires_a_subscription(self):
        # An unset field is a missing decision; the safe reading of a
        # missing decision on a paid product is that it is paid.
        self.assertEqual(
            entitlements.strategy_verdict([], TODAY, None), entitlements.NEEDS_ACTIVE
        )
        self.assertEqual(
            entitlements.strategy_verdict([CURRENT_STANDARD], TODAY, None),
            entitlements.ALLOWED,
        )

    def test_a_strategy_demanding_an_unknown_tier_is_satisfied_by_any_active_sub(self):
        # tier_rank of an unknown required tier is 0, so it cannot lock out
        # a paying user by typo. The fail-closed direction here is on the
        # HELD tier, not the required one.
        self.assertEqual(
            entitlements.strategy_verdict([CURRENT_STANDARD], TODAY, "platinum"),
            entitlements.ALLOWED,
        )

    def test_duplicate_overlapping_periods_cannot_widen_coverage(self):
        doubled = [LAPSED, LAPSED, LAPSED]
        self.assertEqual(
            entitlements.strategy_verdict(doubled, TODAY, "standard"),
            entitlements.NEEDS_ACTIVE,
        )


class TestExplain(unittest.TestCase):
    def test_explain_reports_active_state_tier_and_every_period(self):
        summary = entitlements.explain([LAPSED, CURRENT_PRO], TODAY)
        self.assertTrue(summary["active"])
        self.assertEqual(summary["tier"], "pro")
        self.assertEqual(len(summary["periods"]), 2)
        self.assertEqual(summary["periods"][0]["start"], "2025-01-15")
        self.assertEqual(summary["periods"][0]["end"], "2025-12-15")
        self.assertIsNone(summary["periods"][1]["end"])

    def test_explain_on_an_empty_history_reports_locked_without_throwing(self):
        summary = entitlements.explain([], TODAY)
        self.assertFalse(summary["active"])
        self.assertEqual(summary["tier"], "none")
        self.assertEqual(summary["periods"], [])

    def test_explain_agrees_with_the_verdict_it_describes(self):
        # The endpoint only explains; the gate is strategy_verdict. They
        # must not disagree, or the UI shows an unlocked card that the
        # server then refuses.
        for periods in ([], [LAPSED], [CURRENT_STANDARD], [CURRENT_PRO]):
            summary = entitlements.explain(periods, TODAY)
            verdict = entitlements.strategy_verdict(periods, TODAY, "standard")
            self.assertEqual(
                summary["active"], verdict != entitlements.NEEDS_ACTIVE
            )


if __name__ == "__main__":
    unittest.main()
