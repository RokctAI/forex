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

"""Risk presets resolved to concrete parameters — frappe-free pure module.

The decided rule: **a preset is a shortcut for picking numbers, not a
reference to a name.** When a user chooses "balanced" we resolve it to four
parameters and store *those*. Redefining what "balanced" means next quarter
then changes what NEW users get and nothing about existing ones. Storing the
name instead would silently re-risk every account the day the table changed —
the account is real money, and a definition change is not a user decision.

The four parameters are the complete risk surface a strategy is allowed to
see. A strategy asks the risk layer for permission before every entry; it
never reads a preset name and never has its own opinion about size.

The second decided rule: **absence resolves to the most conservative
setting, never to unrestricted.** A missing risk profile, an unregistered
adapter, a null row, an unknown preset name, a corrupt value — every one of
them lands on [most_conservative]. There is no code path in this module that
returns a wider allowance than the caller could prove it was entitled to.
That is why every function here returns a fully-populated parameter dict
rather than an Optional: a caller cannot forget to handle None.
"""

from typing import Any, Dict, Mapping, Optional

# The four resolved parameters. Percentages are of account equity, not of
# balance — a drawdown guard that ignores open losses is not a guard.
RISK_PER_TRADE_PCT = "risk_per_trade_pct"
DAILY_LOSS_PCT = "daily_loss_pct"
MAX_DRAWDOWN_PCT = "max_drawdown_pct"
MAX_OPEN_POSITIONS = "max_open_positions"

PARAMETER_NAMES = (
    RISK_PER_TRADE_PCT,
    DAILY_LOSS_PCT,
    MAX_DRAWDOWN_PCT,
    MAX_OPEN_POSITIONS,
)

# Integer-valued parameters — resolved as ints so a stored 2.7 can never
# become "2.7 open positions" in a comparison.
_INTEGER_PARAMETERS = (MAX_OPEN_POSITIONS,)

CONSERVATIVE = "conservative"
BALANCED = "balanced"
AGGRESSIVE = "aggressive"

# The preset table. These are starting points chosen to be defensible, NOT
# measured against any backtest — nothing in this repository has had market
# data through it. Editing a row here changes what new users resolve to and
# deliberately does not touch anybody already running.
PRESETS: Dict[str, Dict[str, float]] = {
    CONSERVATIVE: {
        RISK_PER_TRADE_PCT: 0.25,
        DAILY_LOSS_PCT: 1.0,
        MAX_DRAWDOWN_PCT: 5.0,
        MAX_OPEN_POSITIONS: 1,
    },
    BALANCED: {
        RISK_PER_TRADE_PCT: 0.5,
        DAILY_LOSS_PCT: 2.0,
        MAX_DRAWDOWN_PCT: 10.0,
        MAX_OPEN_POSITIONS: 2,
    },
    AGGRESSIVE: {
        RISK_PER_TRADE_PCT: 1.0,
        DAILY_LOSS_PCT: 4.0,
        MAX_DRAWDOWN_PCT: 20.0,
        MAX_OPEN_POSITIONS: 4,
    },
}

# Hard ceilings applied to EVERY resolved value, including values read back
# from a stored row. A stored profile is trusted to be a real past decision,
# but it is not trusted to be uncorrupted: a row claiming 90% risk per trade
# is a bug or an attack, not a preference. Clamping only ever reduces.
CEILINGS: Dict[str, float] = {
    RISK_PER_TRADE_PCT: 2.0,
    DAILY_LOSS_PCT: 6.0,
    MAX_DRAWDOWN_PCT: 25.0,
    MAX_OPEN_POSITIONS: 5,
}


def _coerce(name: str, value: Any) -> Optional[float]:
    """A stored value as a usable number, or None when it is unusable.

    None means "fall back to the conservative floor for this parameter" —
    never "no limit". Booleans are rejected explicitly: in Python `True` is
    numeric, and a stored True would otherwise resolve to a 1% risk cap.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # NaN fails every comparison, so it would slip past a plain `<= 0` guard
    # and then poison every downstream sizing multiplication.
    if number != number:
        return None
    if number <= 0:
        # Zero and negatives are not "no risk allowed" — they are a broken
        # row. A real "stop trading" is the active flag on the assignment,
        # not a zero here.
        return None
    if name in _INTEGER_PARAMETERS:
        number = float(int(number))
        if number < 1:
            return None
    return number


def _clamp(name: str, value: float) -> float:
    ceiling = CEILINGS[name]
    clamped = min(value, ceiling)
    return int(clamped) if name in _INTEGER_PARAMETERS else float(clamped)


def most_conservative() -> Dict[str, float]:
    """The tightest value available for each parameter, computed across the
    whole preset table rather than hardcoded.

    Deriving it means a future preset that is tighter than `conservative`
    automatically becomes the fallback floor, and it is impossible to add a
    preset while forgetting to update the safe default.
    """
    return {
        name: min(_clamp(name, preset[name]) for preset in PRESETS.values())
        for name in PARAMETER_NAMES
    }


def resolve(preset_name: Optional[str]) -> Dict[str, float]:
    """Resolve a preset NAME to parameters, for the moment a user picks one.

    Unknown names, None and blank strings all resolve to
    [most_conservative] — an unrecognised preset is a bug, and the safe
    reading of a bug is the tightest setting, not the last one that parsed.
    """
    if not preset_name or not isinstance(preset_name, str):
        return most_conservative()
    preset = PRESETS.get(preset_name.strip().lower())
    if preset is None:
        return most_conservative()
    return {name: _clamp(name, preset[name]) for name in PARAMETER_NAMES}


def resolve_stored(stored: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    """Resolve the parameters a user is actually running from a stored risk
    profile row.

    This is the read path the strategy layer uses, and it is the one that
    must never widen. Per parameter:

    - a usable stored value wins, clamped down to its ceiling — this is the
      whole point of storing resolved numbers, so a later edit to [PRESETS]
      cannot move an existing account;
    - a missing, null, zero, negative, NaN, boolean or unparseable value
      falls back to that parameter's [most_conservative] floor.

    A wholly absent row (`None`) is the same case as every field being
    missing, so it lands on [most_conservative] — this is the "null risk
    adapter" rule, and it holds per-field, not just for the whole row: a
    half-written profile cannot leave one dimension unrestricted.
    """
    floor = most_conservative()
    if not isinstance(stored, Mapping):
        return floor
    resolved: Dict[str, float] = {}
    for name in PARAMETER_NAMES:
        value = _coerce(name, stored.get(name))
        resolved[name] = floor[name] if value is None else _clamp(name, value)
    return resolved


def is_at_least_as_safe(
    candidate: Mapping[str, Any], reference: Mapping[str, Any]
) -> bool:
    """Whether [candidate] allows no more risk than [reference] on every
    parameter. Used to check that a proposed profile change is a tightening
    (which can apply immediately) rather than a loosening (which is a user
    decision needing explicit confirmation).

    Both sides go through [resolve_stored] first, so this compares what
    would actually be enforced rather than what was written down.
    """
    left = resolve_stored(candidate)
    right = resolve_stored(reference)
    return all(left[name] <= right[name] for name in PARAMETER_NAMES)


def preset_names() -> tuple:
    """The selectable preset names, tightest first — the order a picker
    should offer them in, derived from the table rather than restated."""
    return tuple(
        sorted(PRESETS, key=lambda name: PRESETS[name][RISK_PER_TRADE_PCT])
    )
