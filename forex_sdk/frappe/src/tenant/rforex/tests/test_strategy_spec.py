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

"""Strategy versions, blocked-status handling and spec validation, pinned
standalone (no frappe, no site — `python -m unittest`).

The boundaries these tests exist to hold: **a published spec is frozen**,
**upgrades are opt-in**, and **a blocked version stops the bot no matter
what any other row says.**
"""

import importlib.util
import os
import unittest

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "strategy_spec.py")
_spec_loader = importlib.util.spec_from_file_location("rforex_strategy_spec", _MODULE_PATH)
strategy_spec = importlib.util.module_from_spec(_spec_loader)
_spec_loader.loader.exec_module(strategy_spec)


def valid_spec(**overrides):
    """The London breakout spec as the cBot's defaults describe it."""
    spec = {
        "kind": strategy_spec.KIND_SESSION_BREAKOUT,
        "symbol": "GBPJPY",
        "session_timezone": "Europe/London",
        "range_start": "00:00",
        "signal": "09:00",
        "trading_days": ["Tue"],
        "entry_buffer": {"mode": "atr_multiple", "value": 0.05},
        "stop": {"mode": "opposite_range_side"},
        "min_range": {"mode": "atr_multiple", "value": 0.25},
        "target_r": 1.0,
    }
    spec.update(overrides)
    return spec


V1 = {"version": 1, "status": strategy_spec.STATUS_RETIRED}
V2 = {"version": 2, "status": strategy_spec.STATUS_PUBLISHED}
V3_DRAFT = {"version": 3, "status": strategy_spec.STATUS_DRAFT}
V2_BLOCKED = {"version": 2, "status": strategy_spec.STATUS_BLOCKED, "blocked_reason": "Sizing bug"}


class TestImmutability(unittest.TestCase):
    def test_only_a_draft_is_editable(self):
        self.assertTrue(strategy_spec.is_editable(strategy_spec.STATUS_DRAFT))
        for status in (
            strategy_spec.STATUS_PUBLISHED,
            strategy_spec.STATUS_RETIRED,
            strategy_spec.STATUS_BLOCKED,
        ):
            self.assertFalse(strategy_spec.is_editable(status))

    def test_a_blocked_version_stays_frozen_so_the_post_mortem_has_something_to_read(self):
        self.assertFalse(strategy_spec.is_editable(strategy_spec.STATUS_BLOCKED))

    def test_unknown_status_is_not_editable(self):
        self.assertFalse(strategy_spec.is_editable("whatever"))
        self.assertFalse(strategy_spec.is_editable(None))


class TestStatusTransitions(unittest.TestCase):
    def test_draft_may_be_published(self):
        self.assertTrue(
            strategy_spec.can_transition(
                strategy_spec.STATUS_DRAFT, strategy_spec.STATUS_PUBLISHED
            )
        )

    def test_published_may_be_blocked(self):
        self.assertTrue(
            strategy_spec.can_transition(
                strategy_spec.STATUS_PUBLISHED, strategy_spec.STATUS_BLOCKED
            )
        )

    def test_a_retired_version_may_still_be_blocked(self):
        # Grandfathered users are exactly who a safety block must reach.
        self.assertTrue(
            strategy_spec.can_transition(
                strategy_spec.STATUS_RETIRED, strategy_spec.STATUS_BLOCKED
            )
        )

    def test_a_blocked_version_may_be_unblocked_after_a_fix(self):
        self.assertTrue(
            strategy_spec.can_transition(
                strategy_spec.STATUS_BLOCKED, strategy_spec.STATUS_PUBLISHED
            )
        )

    def test_nothing_returns_to_draft(self):
        for status in (
            strategy_spec.STATUS_PUBLISHED,
            strategy_spec.STATUS_RETIRED,
            strategy_spec.STATUS_BLOCKED,
        ):
            self.assertFalse(
                strategy_spec.can_transition(status, strategy_spec.STATUS_DRAFT)
            )

    def test_unknown_statuses_are_refused_on_both_sides(self):
        self.assertFalse(strategy_spec.can_transition("live", strategy_spec.STATUS_PUBLISHED))
        self.assertFalse(strategy_spec.can_transition(strategy_spec.STATUS_DRAFT, "live"))
        self.assertFalse(strategy_spec.can_transition(None, None))


class TestRunnability(unittest.TestCase):
    def test_published_runs(self):
        self.assertTrue(strategy_spec.is_runnable(strategy_spec.STATUS_PUBLISHED))

    def test_retired_still_runs_for_whoever_pinned_it(self):
        # Retirement removes a version from the shelf; it does not force an
        # upgrade on anybody already running it.
        self.assertTrue(strategy_spec.is_runnable(strategy_spec.STATUS_RETIRED))

    def test_draft_never_runs(self):
        self.assertFalse(strategy_spec.is_runnable(strategy_spec.STATUS_DRAFT))

    def test_blocked_never_runs(self):
        self.assertFalse(strategy_spec.is_runnable(strategy_spec.STATUS_BLOCKED))

    def test_unknown_status_never_runs(self):
        self.assertFalse(strategy_spec.is_runnable("probably_fine"))
        self.assertFalse(strategy_spec.is_runnable(None))


class TestAssignmentVerdict(unittest.TestCase):
    def test_an_active_pin_on_a_published_version_runs(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, V2), strategy_spec.RUN
        )

    def test_an_active_pin_on_a_retired_version_still_runs(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, V1), strategy_spec.RUN
        )

    def test_a_blocked_version_force_stops(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, V2_BLOCKED),
            strategy_spec.STOP_BLOCKED,
        )

    def test_blocking_beats_the_users_own_active_flag(self):
        # The block check runs first, deliberately: nothing on the user's
        # row may keep a blocked version alive.
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 0}, V2_BLOCKED),
            strategy_spec.STOP_BLOCKED,
        )

    def test_a_paused_user_does_not_run(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 0}, V2), strategy_spec.STOP_PAUSED
        )

    def test_no_assignment_does_not_run(self):
        self.assertEqual(
            strategy_spec.assignment_verdict(None, V2), strategy_spec.STOP_UNASSIGNED
        )

    def test_a_dangling_pin_does_not_fall_forward_onto_the_latest_version(self):
        # Silently running "whatever is newest" is the exact behaviour
        # versioning exists to prevent.
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, None),
            strategy_spec.STOP_UNASSIGNED,
        )

    def test_a_pin_on_a_draft_does_not_run(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, V3_DRAFT),
            strategy_spec.STOP_NOT_RUNNABLE,
        )

    def test_an_unknown_status_fails_closed(self):
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, {"version": 4, "status": "beta"}),
            strategy_spec.STOP_NOT_RUNNABLE,
        )


class TestVersionSelection(unittest.TestCase):
    def test_compare_orders_by_number(self):
        self.assertEqual(strategy_spec.compare_versions(1, 2), -1)
        self.assertEqual(strategy_spec.compare_versions(3, 3), 0)
        self.assertEqual(strategy_spec.compare_versions(5, 2), 1)

    def test_unparseable_versions_sort_below_real_ones(self):
        self.assertEqual(strategy_spec.compare_versions("x", 1), -1)
        self.assertEqual(strategy_spec.compare_versions(None, 1), -1)

    def test_latest_publishable_ignores_drafts_retired_and_blocked(self):
        latest = strategy_spec.latest_publishable([V1, V2, V3_DRAFT])
        self.assertEqual(latest["version"], 2)

    def test_latest_publishable_is_none_when_nothing_is_published(self):
        self.assertIsNone(strategy_spec.latest_publishable([V1, V3_DRAFT]))

    def test_latest_publishable_is_none_for_an_empty_catalog(self):
        self.assertIsNone(strategy_spec.latest_publishable([]))

    def test_upgrade_is_offered_when_a_newer_published_version_exists(self):
        self.assertEqual(strategy_spec.upgrade_offer(1, [V1, V2]), 2)

    def test_no_upgrade_offered_when_already_on_the_newest(self):
        self.assertIsNone(strategy_spec.upgrade_offer(2, [V1, V2]))

    def test_a_newer_draft_is_not_offered(self):
        self.assertIsNone(strategy_spec.upgrade_offer(2, [V2, V3_DRAFT]))

    def test_a_newer_blocked_version_is_not_offered(self):
        blocked_v3 = {"version": 3, "status": strategy_spec.STATUS_BLOCKED}
        self.assertIsNone(strategy_spec.upgrade_offer(2, [V2, blocked_v3]))

    def test_an_offer_is_only_an_offer_it_does_not_change_the_verdict(self):
        # A user pinned to v1 with v2 available keeps running v1.
        self.assertEqual(strategy_spec.upgrade_offer(1, [V1, V2]), 2)
        self.assertEqual(
            strategy_spec.assignment_verdict({"active": 1}, V1), strategy_spec.RUN
        )


class TestSpecValidation(unittest.TestCase):
    def test_the_shipped_london_breakout_spec_is_valid(self):
        self.assertEqual(strategy_spec.validate_spec(valid_spec()), [])
        self.assertTrue(strategy_spec.is_valid_spec(valid_spec()))

    def test_a_non_object_is_rejected(self):
        self.assertTrue(strategy_spec.validate_spec("GBPJPY"))

    def test_every_missing_required_key_is_reported_not_just_the_first(self):
        errors = strategy_spec.validate_spec({})
        self.assertGreaterEqual(len(errors), 9)

    def test_an_unsupported_kind_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(kind="mean_reversion"))
        self.assertTrue(any("Unsupported kind" in e for e in errors))

    def test_a_fixed_offset_timezone_is_refused(self):
        # 'GMT+2' is the mistake that silently breaks DST.
        errors = strategy_spec.validate_spec(valid_spec(session_timezone="GMT+2"))
        self.assertTrue(any("IANA" in e for e in errors))

    def test_a_range_that_wraps_past_midnight_is_refused_and_names_the_open_question(self):
        # The broker-daily-boundary answer to the range-start question
        # (17:00 New York) needs this, and it is not supported yet.
        errors = strategy_spec.validate_spec(valid_spec(range_start="22:00", signal="09:00"))
        self.assertTrue(any("wrap past midnight" in e for e in errors))

    def test_a_zero_length_range_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(range_start="09:00", signal="09:00"))
        self.assertTrue(any("earlier in the day" in e for e in errors))

    def test_a_malformed_time_is_refused(self):
        self.assertTrue(strategy_spec.validate_spec(valid_spec(range_start="9am")))
        self.assertTrue(strategy_spec.validate_spec(valid_spec(signal="25:00")))

    def test_an_empty_trading_day_list_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(trading_days=[]))
        self.assertTrue(any("trading_days" in e for e in errors))

    def test_an_unknown_day_name_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(trading_days=["Tue", "Funday"]))
        self.assertTrue(any("Funday" in e for e in errors))

    def test_a_negative_entry_buffer_is_refused(self):
        errors = strategy_spec.validate_spec(
            valid_spec(entry_buffer={"mode": "pips", "value": -1})
        )
        self.assertTrue(any("greater than zero" in e for e in errors))

    def test_an_unknown_distance_mode_is_refused(self):
        errors = strategy_spec.validate_spec(
            valid_spec(entry_buffer={"mode": "percent", "value": 1})
        )
        self.assertTrue(any("entry_buffer.mode" in e for e in errors))

    def test_the_opposite_range_side_stop_needs_no_value(self):
        self.assertEqual(
            strategy_spec.validate_spec(valid_spec(stop={"mode": "opposite_range_side"})), []
        )

    def test_a_pip_stop_without_a_value_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(stop={"mode": "pips"}))
        self.assertTrue(any("stop.value" in e for e in errors))

    def test_a_zero_target_is_refused(self):
        errors = strategy_spec.validate_spec(valid_spec(target_r=0))
        self.assertTrue(any("target_r" in e for e in errors))

    def test_a_boolean_target_is_not_a_number(self):
        errors = strategy_spec.validate_spec(valid_spec(target_r=True))
        self.assertTrue(any("target_r must be a number" in e for e in errors))


class TestPublicVersionView(unittest.TestCase):
    def test_the_catalog_view_carries_no_spec(self):
        view = strategy_spec.public_version_view(dict(V2, spec=valid_spec()))
        self.assertNotIn("spec", view)

    def test_a_blocked_version_exposes_its_reason(self):
        view = strategy_spec.public_version_view(V2_BLOCKED)
        self.assertTrue(view["blocked"])
        self.assertFalse(view["runnable"])
        self.assertEqual(view["blocked_reason"], "Sizing bug")

    def test_a_healthy_version_carries_no_blocked_reason(self):
        view = strategy_spec.public_version_view(dict(V2, blocked_reason="stale text"))
        self.assertFalse(view["blocked"])
        self.assertIsNone(view["blocked_reason"])


if __name__ == "__main__":
    unittest.main()
