# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""One user's pinned strategy assignment — the row that answers "what is
this person's money actually running".

The pin is the point. A user chooses a version and stays on it; a new
version being published changes nothing here until they accept the offer.
The back office has exactly one lever that reaches past the pin, and it is
`blocked` on the version — which STOPS the bot rather than moving it, so the
user's own choice is never silently replaced.

One assignment per (user, strategy). Running two versions of the same
strategy on one account would double the position count against a risk
budget that was resolved for one.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ForexUserStrategy(Document):
    def before_insert(self):
        # if_owner read permission: the user may see their own assignment.
        if self.user and self.owner != self.user:
            self.owner = self.user
        if not self.pinned_on:
            self.pinned_on = now_datetime()

    def validate(self):
        self._one_per_strategy()
        self._version_belongs_to_strategy()
        self._risk_profile_belongs_to_user()
        if self.has_value_changed("pinned_version"):
            self.pinned_on = now_datetime()

    def _one_per_strategy(self):
        clash = frappe.db.get_value(
            "Forex User Strategy",
            {
                "user": self.user,
                "strategy": self.strategy,
                "name": ("!=", self.name or ""),
            },
            "name",
        )
        if clash:
            frappe.throw(
                _(
                    "This user already has an assignment for that strategy. "
                    "Change the pinned version on it rather than adding a "
                    "second row."
                )
            )

    def _version_belongs_to_strategy(self):
        if not self.pinned_version:
            return
        owner_strategy = frappe.db.get_value(
            "Forex Strategy Version", self.pinned_version, "strategy"
        )
        if owner_strategy != self.strategy:
            frappe.throw(
                _("That version belongs to a different strategy.")
            )

    def _risk_profile_belongs_to_user(self):
        if not self.risk_profile:
            return
        profile_user = frappe.db.get_value(
            "Forex Risk Profile", self.risk_profile, "user"
        )
        if profile_user != self.user:
            frappe.throw(_("That risk profile belongs to a different user."))

    def record_verdict(self, verdict):
        """Store why the bot is (or is not) running.

        Called by the serving endpoint on every decision. Written with
        db_set rather than save() so recording a verdict cannot itself fail
        validation and mask the verdict it was trying to record.
        """
        self.db_set(
            {"last_verdict": verdict, "last_verdict_on": now_datetime()},
            update_modified=False,
        )
