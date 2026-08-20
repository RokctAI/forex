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

"""A user's risk limits, stored as RESOLVED PARAMETERS rather than a preset
name.

The decision, and why it is not just a normalisation preference: if this row
said `preset = "balanced"` and nothing more, then editing what "balanced"
means — a perfectly ordinary product change — would instantly and silently
change the position size on every account that had ever chosen it. Nobody
would have consented to that, and nobody would see it happen. So the preset
is resolved to four numbers at the moment the user picks it, and those
numbers are what the strategy layer reads forever after. The preset name
survives only as a label.

The second half of the same decision lives in rforex.risk_presets: a missing
or unreadable value here falls back to the most conservative setting, never
to unrestricted. Absence is not permission.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Kept in sync with rforex/risk_presets.py's CEILINGS. Duplicated rather
# than imported, matching rlms's MIN_GRADE/MAX_GRADE precedent: these are
# four scalars, and the desk form needs a bound even if the rules module is
# unavailable. risk_presets remains the authority — it clamps on every read,
# so a row that somehow got past this check still cannot widen at runtime.
CEILINGS = {
    "risk_per_trade_pct": 2.0,
    "daily_loss_pct": 6.0,
    "max_drawdown_pct": 25.0,
    "max_open_positions": 5,
}


class ForexRiskProfile(Document):
    def before_insert(self):
        # if_owner read permission: the user may see their own limits.
        if self.user and self.owner != self.user:
            self.owner = self.user
        if not self.resolved_on:
            self.resolved_on = now_datetime()

    def validate(self):
        self._one_per_user()
        self._validate_limits()
        self._validate_currency()
        if any(self.has_value_changed(f) for f in CEILINGS):
            self.resolved_on = now_datetime()

    def _one_per_user(self):
        clash = frappe.db.get_value(
            "Forex Risk Profile",
            {"user": self.user, "name": ("!=", self.name or "")},
            "name",
        )
        if clash:
            frappe.throw(
                _("This user already has a risk profile. Edit that one.")
            )

    def _validate_limits(self):
        for field, ceiling in CEILINGS.items():
            value = self.get(field)
            if value is None or value <= 0:
                frappe.throw(
                    _("{0} must be greater than zero.").format(
                        self.meta.get_label(field)
                    )
                )
            if value > ceiling:
                frappe.throw(
                    _("{0} cannot exceed {1}.").format(
                        self.meta.get_label(field), ceiling
                    )
                )
        if int(self.max_open_positions) != float(self.max_open_positions):
            frappe.throw(_("Max Open Positions must be a whole number."))

    def _validate_currency(self):
        if not self.account_currency:
            return
        code = self.account_currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            frappe.throw(
                _("Account Currency must be a 3-letter ISO 4217 code.")
            )
        self.account_currency = code
