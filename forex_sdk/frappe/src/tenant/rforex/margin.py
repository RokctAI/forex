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

"""Account equity, margin level and freshness — frappe-free pure module.

This is the arithmetic behind the dashboard's headline numbers:

    equity       = balance + Σ unrealised P/L of open positions
    free margin  = equity - used margin
    margin level = equity / used margin, as a percentage

Two rules run through the whole module, and both exist because a number
here becomes a position size somewhere else:

1. **Nothing defaults.** There is no "assume zero balance", no "treat a
   missing price as break-even", no silent skip of a position that failed to
   parse. Every one of those raises. A dashboard that renders an error is a
   nuisance; a dashboard that renders a confident wrong equity is how an
   account gets sized off a number nobody computed.

2. **Every amount carries its currency.** A broker account is denominated in
   one currency and the balance, the P/L and the margin are all in it. The
   code is stored beside the numbers because it cannot be recovered
   afterwards — an amount of 4,812.55 with the currency lost is not a value,
   it's a rumour. Mixing currencies in one snapshot raises rather than
   summing.

Reading the numbers off a broker is NOT this module's job and is not
implemented anywhere in this repository yet (see api/account.py). This
module is the part that is safe to write before the connector exists,
because it can be proven correct without one.
"""

from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional

# How old a broker snapshot may be before the dashboard must label it stale.
# Balance and margin move on every tick; a minute-old margin level shown
# without a timestamp is the same failure mode as a made-up one.
MAX_SNAPSHOT_AGE = timedelta(seconds=30)

# Margin-level bands, in percent. These are the conventional retail-broker
# boundaries (margin call at 100%, stop-out at 50%); the warning band above
# them is ours, so the UI can say something before the broker does. The
# real numbers are broker- and account-specific: when the connector lands,
# these become defaults the broker's own values override.
STOP_OUT_LEVEL_PCT = 50.0
MARGIN_CALL_LEVEL_PCT = 100.0
WARNING_LEVEL_PCT = 200.0

STATE_NO_POSITIONS = "no_positions"
STATE_HEALTHY = "healthy"
STATE_WARNING = "warning"
STATE_MARGIN_CALL = "margin_call"
STATE_STOP_OUT = "stop_out"


class MissingMarketData(ValueError):
    """A required input was absent or unusable.

    A distinct type so callers cannot accidentally swallow it with the
    generic `except ValueError` they use for user input — this one means
    "do not show the user a number", and it must reach the surface.
    """


def _amount(value: Any, label: str) -> float:
    """A monetary input as a float, or a raise. Never a default."""
    if value is None:
        raise MissingMarketData("{0} is missing.".format(label))
    if isinstance(value, bool):
        raise MissingMarketData("{0} is a boolean, not an amount.".format(label))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MissingMarketData(
            "{0} is not a number: {1!r}.".format(label, value)
        )
    if number != number or number in (float("inf"), float("-inf")):
        raise MissingMarketData("{0} is not finite: {1!r}.".format(label, value))
    return number


def normalise_currency(code: Any) -> str:
    """A currency code, uppercased, or a raise.

    Deliberately strict: three ASCII letters. A blank, a None or a symbol
    like '$' would all be a lost currency, which is the failure this rule
    exists to prevent.
    """
    if not isinstance(code, str):
        raise MissingMarketData("Currency code is missing.")
    cleaned = code.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise MissingMarketData(
            "Currency code must be a 3-letter ISO 4217 code; got {0!r}.".format(code)
        )
    return cleaned


def unrealised_total(
    positions: Iterable[Mapping[str, Any]], account_currency: Any
) -> float:
    """Σ unrealised P/L across open positions, in the account currency.

    Every position must state its own currency and it must match the
    account's. A broker CAN report P/L already converted — but "can" is not
    "did", and summing a JPY figure into a USD equity is a mistake that
    looks like a working dashboard right up until it sizes a trade.
    """
    account = normalise_currency(account_currency)
    total = 0.0
    for index, position in enumerate(positions or []):
        if not isinstance(position, Mapping):
            raise MissingMarketData(
                "Position at index {0} is not a record.".format(index)
            )
        label = "Position {0} ({1})".format(index, position.get("id") or "unlabelled")
        currency = normalise_currency(position.get("currency"))
        if currency != account:
            raise MissingMarketData(
                "{0} is denominated in {1} but the account is in {2}; this "
                "module does not convert.".format(label, currency, account)
            )
        total += _amount(position.get("unrealised_pl"), label + " unrealised P/L")
    return total


def equity(
    balance: Any, positions: Iterable[Mapping[str, Any]], account_currency: Any
) -> float:
    """Account equity: balance plus every open position's unrealised P/L.

    Note the ordering of the guard — the balance is validated even when
    there are no positions, so an account with a missing balance and a flat
    book raises rather than reporting an equity of zero.
    """
    account = normalise_currency(account_currency)
    return _amount(balance, "Balance") + unrealised_total(positions, account)


def free_margin(equity_amount: Any, used_margin: Any) -> float:
    """Equity minus margin currently tied up. May legitimately be negative —
    that IS the margin call, and clamping it to zero would hide it."""
    return _amount(equity_amount, "Equity") - _amount(used_margin, "Used margin")


def margin_level_pct(equity_amount: Any, used_margin: Any) -> Optional[float]:
    """Margin level as a percentage, or None when nothing is at risk.

    None means "undefined, because used margin is zero" — an account with
    no open positions has no margin level. It is emphatically NOT infinity
    (which formats as 'inf' in a UI) and NOT zero (which is the stop-out
    band, i.e. exactly backwards). Callers must render the absence.
    """
    used = _amount(used_margin, "Used margin")
    if used < 0:
        raise MissingMarketData("Used margin cannot be negative.")
    if used == 0:
        return None
    return (_amount(equity_amount, "Equity") / used) * 100.0


def margin_state(level_pct: Optional[float]) -> str:
    """Which band a margin level falls in. None -> no positions.

    Boundaries are inclusive at the top of the worse band: exactly 100% is
    a margin call, not a warning. On a threshold, the pessimistic reading is
    the correct one.
    """
    if level_pct is None:
        return STATE_NO_POSITIONS
    level = _amount(level_pct, "Margin level")
    if level <= STOP_OUT_LEVEL_PCT:
        return STATE_STOP_OUT
    if level <= MARGIN_CALL_LEVEL_PCT:
        return STATE_MARGIN_CALL
    if level <= WARNING_LEVEL_PCT:
        return STATE_WARNING
    return STATE_HEALTHY


def is_stale(
    as_of: Optional[datetime],
    now: datetime,
    max_age: timedelta = MAX_SNAPSHOT_AGE,
) -> bool:
    """Whether a snapshot is too old to present as current.

    A missing timestamp is stale — an untimed number cannot be shown as
    live. A FUTURE timestamp is stale too: it means the clocks disagree, and
    a snapshot we cannot age is one we cannot vouch for.
    """
    if as_of is None:
        return True
    if not isinstance(as_of, datetime) or not isinstance(now, datetime):
        raise MissingMarketData("Snapshot timestamps must be datetimes.")
    if as_of > now:
        return True
    return (now - as_of) > max_age


def snapshot(
    balance: Any,
    used_margin: Any,
    positions: Iterable[Mapping[str, Any]],
    account_currency: Any,
    as_of: Optional[datetime],
    now: datetime,
    max_age: timedelta = MAX_SNAPSHOT_AGE,
) -> dict:
    """The complete dashboard payload, computed from broker figures.

    Every monetary value in the result sits next to `currency`, and the
    result carries both `as_of` and `stale` so the client never has to guess
    whether it is looking at live numbers. There is no partial success: if
    any input is unusable this raises [MissingMarketData] and the caller
    shows an error state, not a number.
    """
    account = normalise_currency(account_currency)
    equity_amount = equity(balance, positions, account)
    used = _amount(used_margin, "Used margin")
    level = margin_level_pct(equity_amount, used)
    return {
        "currency": account,
        "balance": _amount(balance, "Balance"),
        "equity": equity_amount,
        "used_margin": used,
        "free_margin": free_margin(equity_amount, used),
        "margin_level_pct": level,
        "margin_state": margin_state(level),
        "open_position_count": len(list(positions or [])),
        "as_of": as_of.isoformat() if as_of is not None else None,
        "stale": is_stale(as_of, now, max_age),
        "max_age_seconds": int(max_age.total_seconds()),
    }
