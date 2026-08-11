# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""One covered stretch of a user's forex subscription — the canonical answer
to "was this person entitled to run a bot on this day, and at what tier".

Written ONLY by server-side flows (payment completion, admin backfill),
never by the user's own session. A user who could write their own periods
could grant themselves an unpaid live trading bot, which is why
api/entitlement.record_subscription_period is `frappe.only_for("System
Manager")`.

Overlapping rows are harmless by construction: entitlement resolution
(rforex.entitlements) is a containment scan, so duplicates cannot widen
coverage. Where overlapping periods grant different tiers, the highest one
wins for those days — the user paid for both.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class ForexSubscriptionPeriod(Document):
    def before_insert(self):
        # if_owner read permission: the user may see their own coverage.
        if self.user and self.owner != self.user:
            self.owner = self.user

    def validate(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(_("A subscription period cannot end before it starts."))
        self._validate_amount_currency()

    def _validate_amount_currency(self):
        """An amount without a currency is refused.

        Nothing upstream in the estate enforces this and it cannot be added
        retroactively — once a row exists with 249.00 and no code, the
        currency that was meant is genuinely gone.
        """
        if self.amount and not self.currency:
            frappe.throw(
                _(
                    "An amount needs its currency. A stored amount whose "
                    "currency was never recorded cannot be recovered later."
                )
            )
        if not self.currency:
            return
        code = self.currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            frappe.throw(_("Currency must be a 3-letter ISO 4217 code."))
        self.currency = code
