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

"""Entitlement endpoints.

Two things live here and they are deliberately different in kind:

- `my_entitlements` EXPLAINS. It exists so the UI can say "this strategy
  needs Pro and you're on Standard" instead of showing an unlocked card that
  the server then refuses. It decides nothing. A client that lied about its
  response would gain no access.
- `record_subscription_period` GRANTS, and is therefore
  `frappe.only_for("System Manager")`. A user able to write their own
  coverage could grant themselves an unpaid live trading bot.

The real gate is neither of these — it is applied inside api/strategy.py, on
the endpoints that actually serve a spec.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from .. import entitlements


def get_periods(user):
    """A user's subscription periods as (start, end_or_None, tier) tuples —
    the input shape rforex.entitlements works in.

    Rows with no start_date are dropped rather than defaulted: a period
    whose beginning was never recorded is not a period, and guessing one
    would be inventing coverage.
    """
    rows = frappe.get_all(
        "Forex Subscription Period",
        filters={"user": user},
        fields=["start_date", "end_date", "tier"],
        ignore_permissions=True,
    )
    return [
        (
            getdate(r.start_date),
            getdate(r.end_date) if r.end_date else None,
            r.tier or entitlements.TIER_STANDARD,
        )
        for r in rows
        if r.start_date
    ]


@frappe.whitelist()
def my_entitlements():
    """The app-queryable entitlement summary.

    Returns whether a subscription covers today, the tier it grants, and the
    covered ranges so the catalog can mark each strategy locked or not
    without a round-trip per card.

    Resolution itself stays server-side: api/strategy.get_strategy enforces
    on serving. This endpoint exists so the UI can EXPLAIN a lock rather
    than discover it by being refused.
    """
    user = frappe.session.user
    periods = get_periods(user)
    server_today = getdate(nowdate())
    summary = entitlements.explain(periods, server_today)
    summary["server_date"] = server_today.isoformat()
    return summary


@frappe.whitelist()
def record_subscription_period(user, start_date, end_date=None, tier=None,
                               amount=None, currency=None, source=None):
    """Server-side write of one covered period — called by the payment
    completion flow or an admin backfill, never by the user's own session.

    System Manager only. This is the endpoint that grants access to a
    product that trades real money; a user who could call it could run a
    live bot for free.

    Idempotent by (user, start_date): a renewal extending the same period
    updates the existing row rather than duplicating it. Duplicates that do
    slip through cannot widen access — entitlement resolution is a
    containment scan — but they would make the billing history unreadable.

    An amount is refused without a currency, matching the DocType's own
    validation: an amount whose currency was never recorded cannot be
    recovered later.
    """
    frappe.only_for("System Manager")

    start = getdate(start_date)
    end = getdate(end_date) if end_date else None
    if end and end < start:
        frappe.throw(_("A subscription period cannot end before it starts."))
    if amount and not currency:
        frappe.throw(_("An amount needs its currency."))

    tier = (tier or entitlements.TIER_STANDARD).strip().lower()
    if tier not in (entitlements.TIER_STANDARD, entitlements.TIER_PRO):
        frappe.throw(
            _("Unknown tier {0}. Use 'standard' or 'pro'.").format(tier)
        )

    existing = frappe.db.get_value(
        "Forex Subscription Period",
        {"user": user, "start_date": start},
        "name",
    )
    if existing:
        doc = frappe.get_doc("Forex Subscription Period", existing)
        doc.end_date = end
        doc.tier = tier
        doc.amount = amount
        doc.currency = currency
        doc.source = source
        doc.save(ignore_permissions=True)
        return {"name": doc.name, "updated": True}

    doc = frappe.get_doc(
        {
            "doctype": "Forex Subscription Period",
            "user": user,
            "start_date": start,
            "end_date": end,
            "tier": tier,
            "amount": amount,
            "currency": currency,
            "source": source,
        }
    )
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "updated": False}
