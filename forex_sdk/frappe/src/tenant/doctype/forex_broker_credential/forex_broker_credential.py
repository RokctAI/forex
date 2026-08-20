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

"""One user's cTrader OAuth credentials.

These tokens can move money. That single fact drives every choice in this
DocType, and each one is a deliberate departure from the nearest precedent
in the estate — `pay`'s `Saved Card`, which stores its gateway token as a
plain `Data` field and hands it back to the client. Three differences:

1. **`Password` fieldtype, not `Data`.** Frappe keeps `Password` values in
   the `__Auth` table rather than in this DocType's own table. They are not
   in a `SELECT *`, not in a report, not in an export, and not in the
   `frappe.db.get_value` a future maintainer reaches for out of habit. The
   only read path is `doc.get_password('access_token')`, which is explicit
   enough to notice in review.

2. **`permlevel: 1` on both token fields.** Password fields are already
   masked in ordinary document reads, but the owner of this row can fetch it
   through the generic resource API, and "masked" is a property of Frappe's
   serialisation rather than of the data. Level 1 is granted to System
   Manager only, so the token fields are outside the owner's own read
   permission entirely. Belt and braces, on the one row where a mistake is
   somebody's trading account.

3. **No whitelisted method returns them, ever.** api/credential.py has a
   single public projection helper and it is the only thing endpoints
   return. That is enforced by a test-visible constant
   (`NEVER_RETURNED_FIELDS`) rather than by remembering.

The user still needs to see whether they are connected, to which account,
and whether it is about to expire — so all of that is in ordinary
non-secret fields, readable by the owner.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Fieldnames that must never appear in any API response. Named here, next to
# the schema, so a new secret field gets added to this tuple at the moment it
# is created rather than at the moment it leaks.
SECRET_FIELDS = ("access_token", "refresh_token")


class ForexBrokerCredential(Document):
    def before_insert(self):
        # if_owner read permission: the user may see their own connection
        # status. The secrets are excluded from that by permlevel.
        if self.user and self.owner != self.user:
            self.owner = self.user

    def validate(self):
        self._one_per_user_broker_environment()
        self._validate_currency()

    def _one_per_user_broker_environment(self):
        clash = frappe.db.get_value(
            "Forex Broker Credential",
            {
                "user": self.user,
                "broker": self.broker,
                "environment": self.environment,
                "name": ("!=", self.name or ""),
            },
            "name",
        )
        if clash:
            frappe.throw(
                _(
                    "This user already has {0} {1} credentials. Reconnecting "
                    "updates that row rather than adding a second one — two "
                    "live token pairs for one account means one of them is "
                    "stale and nothing can tell which."
                ).format(self.broker, self.environment)
            )

    def _validate_currency(self):
        if not self.account_currency:
            return
        code = self.account_currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            frappe.throw(
                _("Account Currency must be a 3-letter ISO 4217 code.")
            )
        self.account_currency = code

    def access_token_value(self):
        """The decrypted access token, for server-side broker calls only.

        Named as a method rather than exposed as a property so that every
        call site is greppable: `access_token_value(` finds every place in
        the codebase that touches the secret.
        """
        return self.get_password("access_token", raise_exception=False)

    def refresh_token_value(self):
        """The decrypted refresh token, for the server-side token exchange
        only. See [access_token_value]."""
        return self.get_password("refresh_token", raise_exception=False)
