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

"""A named strategy family. Deliberately almost empty: the strategy itself
carries no behaviour and no parameters — everything a bot reads lives on a
`Forex Strategy Version`, which is immutable once published.

This row exists so a user can pin "London Breakout" rather than "version 4
of some numbers", and so versions have something to hang off.

Note what is NOT here: no `current_version` pointer. A pointer would be a
second place the truth lives, and the first time it disagreed with the
version rows somebody's bot would run the wrong spec. The latest publishable
version is computed from the version rows on every read
(rforex.strategy_spec.latest_publishable).
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document

# A machine identifier, not a label: lowercase, digits, underscores.
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ForexStrategy(Document):
    def validate(self):
        if not self.strategy_key or not _KEY_PATTERN.match(self.strategy_key):
            frappe.throw(
                _(
                    "Strategy Key must be lowercase letters, digits and "
                    "underscores, starting with a letter (e.g. london_breakout)."
                )
            )

    def on_update(self):
        # A published key is pinned by user rows; renaming it would orphan
        # them silently. Caught here rather than left to a foreign key,
        # because Frappe links point at `name` (a hash) and would not notice.
        if not self.is_new() and self.has_value_changed("strategy_key"):
            in_use = frappe.db.count("Forex User Strategy", {"strategy": self.name})
            if in_use:
                frappe.throw(
                    _(
                        "Strategy Key cannot change: {0} user assignment(s) "
                        "reference this strategy."
                    ).format(in_use)
                )
