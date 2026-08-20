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

"""Risk preset resolution, pinned standalone (no frappe, no site —
`python -m unittest`).

Loaded by file path rather than package import, matching agent/lms's
tests: workspace python modules import through an `{app_name}` placeholder
and only resolve inside a composed app; risk_presets.py is deliberately
frappe-free so this test runs anywhere python does.

The boundary these tests exist to hold: **absence never widens risk.**
"""

import importlib.util
import os
import unittest

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "risk_presets.py")
_spec = importlib.util.spec_from_file_location("rforex_risk_presets", _MODULE_PATH)
risk_presets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(risk_presets)

SAFE = risk_presets.most_conservative()


class TestMostConservative(unittest.TestCase):
    def test_is_derived_from_the_table_not_hardcoded(self):
        # Every parameter's floor must equal the tightest value any preset
        # offers — so adding a tighter preset moves the floor automatically.
        for name in risk_presets.PARAMETER_NAMES:
            tightest = min(p[name] for p in risk_presets.PRESETS.values())
            self.assertEqual(SAFE[name], tightest)

    def test_matches_the_conservative_preset_today(self):
        self.assertEqual(SAFE, risk_presets.resolve(risk_presets.CONSERVATIVE))

    def test_is_strictly_tighter_than_aggressive(self):
        aggressive = risk_presets.resolve(risk_presets.AGGRESSIVE)
        for name in risk_presets.PARAMETER_NAMES:
            self.assertLess(SAFE[name], aggressive[name])


class TestResolveByName(unittest.TestCase):
    def test_known_preset_resolves_to_its_parameters(self):
        self.assertEqual(
            risk_presets.resolve("balanced"),
            {
                risk_presets.RISK_PER_TRADE_PCT: 0.5,
                risk_presets.DAILY_LOSS_PCT: 2.0,
                risk_presets.MAX_DRAWDOWN_PCT: 10.0,
                risk_presets.MAX_OPEN_POSITIONS: 2,
            },
        )

    def test_name_is_case_and_whitespace_insensitive(self):
        self.assertEqual(risk_presets.resolve("  BALANCED "), risk_presets.resolve("balanced"))

    def test_unknown_name_falls_to_most_conservative(self):
        self.assertEqual(risk_presets.resolve("yolo"), SAFE)

    def test_none_falls_to_most_conservative(self):
        self.assertEqual(risk_presets.resolve(None), SAFE)

    def test_blank_falls_to_most_conservative(self):
        self.assertEqual(risk_presets.resolve("   "), SAFE)

    def test_every_preset_name_resolves_to_a_full_parameter_set(self):
        for name in risk_presets.preset_names():
            resolved = risk_presets.resolve(name)
            self.assertEqual(set(resolved), set(risk_presets.PARAMETER_NAMES))


class TestResolveStored(unittest.TestCase):
    """The read path a running strategy uses. Nothing here may widen."""

    def test_stored_values_win_over_the_preset_table(self):
        # The whole point of storing resolved parameters: a user whose row
        # says 0.5 keeps 0.5 even if 'balanced' is redefined tomorrow.
        stored = {
            risk_presets.RISK_PER_TRADE_PCT: 0.5,
            risk_presets.DAILY_LOSS_PCT: 2.0,
            risk_presets.MAX_DRAWDOWN_PCT: 10.0,
            risk_presets.MAX_OPEN_POSITIONS: 2,
        }
        self.assertEqual(risk_presets.resolve_stored(stored), stored)

    def test_none_row_resolves_to_most_conservative(self):
        # The null risk adapter rule.
        self.assertEqual(risk_presets.resolve_stored(None), SAFE)

    def test_empty_row_resolves_to_most_conservative(self):
        self.assertEqual(risk_presets.resolve_stored({}), SAFE)

    def test_partial_row_falls_back_per_field_not_wholesale(self):
        # A half-written profile must not leave the unwritten dimension open.
        stored = {risk_presets.RISK_PER_TRADE_PCT: 0.4}
        resolved = risk_presets.resolve_stored(stored)
        self.assertEqual(resolved[risk_presets.RISK_PER_TRADE_PCT], 0.4)
        self.assertEqual(resolved[risk_presets.DAILY_LOSS_PCT], SAFE[risk_presets.DAILY_LOSS_PCT])
        self.assertEqual(
            resolved[risk_presets.MAX_OPEN_POSITIONS], SAFE[risk_presets.MAX_OPEN_POSITIONS]
        )

    def test_zero_is_a_broken_row_not_no_risk(self):
        resolved = risk_presets.resolve_stored({risk_presets.RISK_PER_TRADE_PCT: 0})
        self.assertEqual(resolved[risk_presets.RISK_PER_TRADE_PCT], SAFE[risk_presets.RISK_PER_TRADE_PCT])

    def test_negative_falls_back(self):
        resolved = risk_presets.resolve_stored({risk_presets.DAILY_LOSS_PCT: -3})
        self.assertEqual(resolved[risk_presets.DAILY_LOSS_PCT], SAFE[risk_presets.DAILY_LOSS_PCT])

    def test_nan_falls_back_rather_than_poisoning_arithmetic(self):
        resolved = risk_presets.resolve_stored({risk_presets.MAX_DRAWDOWN_PCT: float("nan")})
        self.assertEqual(resolved[risk_presets.MAX_DRAWDOWN_PCT], SAFE[risk_presets.MAX_DRAWDOWN_PCT])

    def test_boolean_true_is_not_one_percent(self):
        # True == 1 in Python; without an explicit guard this would resolve
        # to a 1% risk cap, four times the conservative floor.
        resolved = risk_presets.resolve_stored({risk_presets.RISK_PER_TRADE_PCT: True})
        self.assertEqual(resolved[risk_presets.RISK_PER_TRADE_PCT], SAFE[risk_presets.RISK_PER_TRADE_PCT])

    def test_unparseable_string_falls_back(self):
        resolved = risk_presets.resolve_stored({risk_presets.DAILY_LOSS_PCT: "lots"})
        self.assertEqual(resolved[risk_presets.DAILY_LOSS_PCT], SAFE[risk_presets.DAILY_LOSS_PCT])

    def test_numeric_string_is_accepted(self):
        # Frappe hands Floats back as strings often enough that rejecting
        # them would fall back to conservative for correct rows.
        resolved = risk_presets.resolve_stored({risk_presets.DAILY_LOSS_PCT: "2.0"})
        self.assertEqual(resolved[risk_presets.DAILY_LOSS_PCT], 2.0)

    def test_corrupt_high_value_is_clamped_down_to_the_ceiling(self):
        resolved = risk_presets.resolve_stored({risk_presets.RISK_PER_TRADE_PCT: 90.0})
        self.assertEqual(
            resolved[risk_presets.RISK_PER_TRADE_PCT],
            risk_presets.CEILINGS[risk_presets.RISK_PER_TRADE_PCT],
        )

    def test_open_positions_resolves_to_a_whole_number(self):
        resolved = risk_presets.resolve_stored({risk_presets.MAX_OPEN_POSITIONS: 2.7})
        self.assertEqual(resolved[risk_presets.MAX_OPEN_POSITIONS], 2)
        self.assertIsInstance(resolved[risk_presets.MAX_OPEN_POSITIONS], int)

    def test_fractional_below_one_position_falls_back(self):
        resolved = risk_presets.resolve_stored({risk_presets.MAX_OPEN_POSITIONS: 0.5})
        self.assertEqual(
            resolved[risk_presets.MAX_OPEN_POSITIONS], SAFE[risk_presets.MAX_OPEN_POSITIONS]
        )

    def test_non_mapping_input_resolves_to_most_conservative(self):
        for junk in ("balanced", 5, [], object()):
            self.assertEqual(risk_presets.resolve_stored(junk), SAFE)

    def test_no_input_ever_produces_a_value_above_its_ceiling(self):
        wild = {name: 10 ** 6 for name in risk_presets.PARAMETER_NAMES}
        resolved = risk_presets.resolve_stored(wild)
        for name in risk_presets.PARAMETER_NAMES:
            self.assertLessEqual(resolved[name], risk_presets.CEILINGS[name])


class TestSafetyComparison(unittest.TestCase):
    def test_conservative_is_at_least_as_safe_as_aggressive(self):
        self.assertTrue(
            risk_presets.is_at_least_as_safe(
                risk_presets.resolve(risk_presets.CONSERVATIVE),
                risk_presets.resolve(risk_presets.AGGRESSIVE),
            )
        )

    def test_aggressive_is_not_as_safe_as_conservative(self):
        self.assertFalse(
            risk_presets.is_at_least_as_safe(
                risk_presets.resolve(risk_presets.AGGRESSIVE),
                risk_presets.resolve(risk_presets.CONSERVATIVE),
            )
        )

    def test_a_preset_is_as_safe_as_itself(self):
        balanced = risk_presets.resolve(risk_presets.BALANCED)
        self.assertTrue(risk_presets.is_at_least_as_safe(balanced, balanced))

    def test_loosening_one_dimension_is_enough_to_fail(self):
        base = risk_presets.resolve(risk_presets.CONSERVATIVE)
        looser = dict(base)
        looser[risk_presets.MAX_OPEN_POSITIONS] = base[risk_presets.MAX_OPEN_POSITIONS] + 1
        self.assertFalse(risk_presets.is_at_least_as_safe(looser, base))

    def test_an_empty_candidate_is_safe_against_anything(self):
        # Because an empty candidate resolves to the floor.
        self.assertTrue(
            risk_presets.is_at_least_as_safe({}, risk_presets.resolve(risk_presets.AGGRESSIVE))
        )


class TestPresetOrdering(unittest.TestCase):
    def test_names_come_back_tightest_first(self):
        self.assertEqual(
            risk_presets.preset_names(),
            (risk_presets.CONSERVATIVE, risk_presets.BALANCED, risk_presets.AGGRESSIVE),
        )


if __name__ == "__main__":
    unittest.main()
