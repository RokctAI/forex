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

"""Subscription entitlement rules for forex strategies — frappe-free pure
module.

Mirrors the shape of `agent/lms`'s entitlements.py, with the difference that
matters here: forex has no back-catalog. A lesson recorded last year still
has value to a lapsed student, so LMS asks "were you subscribed WHEN this
aired". A trading strategy has no equivalent — running a bot is a thing that
happens now, with money, and the only question is whether the subscription
covers now.

So the rules are:

- **Browsing is free.** The catalog lists what strategies exist, what they
  claim to do, and which tier they need. Nothing gated, because a paywall
  you can't see the inside of doesn't sell anything.
- **Running is gated on an ACTIVE subscription**, evaluated against the
  server's today. Not "has ever subscribed", not "subscribed when this
  version was published".
- **Tiers gate individual strategies.** A version declares the minimum tier
  it needs; a subscription period carries the tier it granted. Holding a
  lower tier is a different answer from holding none, and the UI says so.

A period is (start_date, end_date, tier) with end_date None meaning still
open. Overlapping periods are harmless: every rule is a containment scan, so
duplicates cannot widen coverage. Where two overlapping periods grant
different tiers, the HIGHEST covering tier wins on that day — the user paid
for both.
"""

from datetime import date
from typing import Optional, Sequence, Tuple

# Tier names, weakest first. Rank is the index; an unknown tier ranks 0,
# i.e. no better than no subscription at all — the fail-closed direction.
TIER_NONE = "none"
TIER_STANDARD = "standard"
TIER_PRO = "pro"

TIER_ORDER = (TIER_NONE, TIER_STANDARD, TIER_PRO)

# (start, end_or_None, tier)
Period = Tuple[date, Optional[date], str]

ALLOWED = "allowed"
NEEDS_ACTIVE = "needs_active"
NEEDS_UPGRADE = "needs_upgrade"


def tier_rank(tier: Optional[str]) -> int:
    """A tier's rank. Unknown, None and blank all rank 0.

    Fail-closed by construction: a typo'd tier in a database row grants
    nothing rather than accidentally sorting above 'pro'.
    """
    if not isinstance(tier, str):
        return 0
    try:
        return TIER_ORDER.index(tier.strip().lower())
    except ValueError:
        return 0


def _contains(period: Period, day: date) -> bool:
    start = period[0]
    end = period[1] if len(period) > 1 else None
    if start is None or day < start:
        return False
    return end is None or day <= end


def active_on(periods: Sequence[Period], day: date) -> bool:
    """Whether any period covers [day]."""
    return any(_contains(p, day) for p in periods or ())


def highest_tier_on(periods: Sequence[Period], day: date) -> str:
    """The best tier covering [day], or [TIER_NONE].

    Highest-wins on overlap: somebody holding both a standard and a pro
    period over the same week paid for pro, and charging them for the
    accident of an overlapping row would be a billing bug wearing an
    entitlement costume.
    """
    best = 0
    for period in periods or ():
        if not _contains(period, day):
            continue
        tier = period[2] if len(period) > 2 else TIER_NONE
        best = max(best, tier_rank(tier))
    return TIER_ORDER[best]


def subscription_active(periods: Sequence[Period], today: date) -> bool:
    """Whether the user has a live subscription of any tier."""
    return active_on(periods, today)


def strategy_verdict(
    periods: Sequence[Period], today: date, required_tier: Optional[str]
) -> str:
    """The one decision the strategy-serving endpoints apply.

    - `allowed`       — serve the spec; the bot may run.
    - `needs_active`  — nothing covers today. Sell a subscription.
    - `needs_upgrade` — covered today, but at a tier below what this
                        strategy needs. Sell the upgrade, and do NOT say
                        "subscribe" to somebody who already pays.

    A strategy with no declared tier requires [TIER_STANDARD], not nothing:
    an unset field is a missing decision, and the safe reading of a missing
    decision on a paid product is that it is paid.
    """
    if not subscription_active(periods, today):
        return NEEDS_ACTIVE
    required = required_tier if required_tier else TIER_STANDARD
    if tier_rank(highest_tier_on(periods, today)) < tier_rank(required):
        return NEEDS_UPGRADE
    return ALLOWED


def explain(periods: Sequence[Period], today: date) -> dict:
    """The summary `my_entitlements` returns so the UI can EXPLAIN a lock
    rather than discover it by being refused.

    This is a description, never a decision — the real gate is
    [strategy_verdict], applied server-side inside the endpoints that serve
    a spec. A client that lied about this payload would gain nothing.
    """
    return {
        "active": subscription_active(periods, today),
        "tier": highest_tier_on(periods, today),
        "periods": [
            {
                "start": p[0].isoformat(),
                "end": p[1].isoformat() if len(p) > 1 and p[1] else None,
                "tier": (p[2] if len(p) > 2 else TIER_NONE),
            }
            for p in (periods or ())
            if p and p[0]
        ],
    }
