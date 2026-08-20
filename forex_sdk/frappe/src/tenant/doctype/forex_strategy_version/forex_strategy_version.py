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

"""One immutable, versioned strategy spec.

**Strategy is data, not code.** This row IS the strategy as far as a running
bot is concerned: it reads the spec, and nothing else decides what it does.
That makes two properties load-bearing, and both are enforced here rather
than by convention:

1. **A published version never changes.** The spec is frozen the moment the
   version leaves draft. Editing a spec that somebody's money is running is
   not an edit, it is a silent change of what their bot does. Change means
   publishing a new version, which they then choose to move to.

2. **Blocking stops bots.** Flipping status to `blocked` is the one action
   that overrides a user's pin, and it stops rather than migrates — see
   rforex.strategy_spec.assignment_verdict. It therefore requires a reason,
   because that reason is shown to every user it stops.

Deliberate permission note: this DocType grants NO role beyond System
Manager, unlike `Forex Strategy`. The spec is the product; handing it to
`All` via the generic resource API would route straight around the
entitlement gate in api/strategy.py. The catalog endpoint reads these rows
server-side and returns only rforex.strategy_spec.public_version_view — the
status and version number, never the parameters.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Relative import into the module's pure-rules package. `src/tenant/rforex/`
# is installed as `{app_name}/rforex/tenant/rforex/` (the persona segment plus
# the doubled module segment visible in manifest.json's whitelisted-method
# targets) while the composer relocates this doctype tree back to
# `{app_name}/rforex/doctype/forex_strategy_version/` (the Frappe-conventional
# module-root path, no persona segment), so `...tenant.rforex` resolves
# without ever naming `{app_name}`.
#
# This is a deliberate departure from rlms, where doctype/ and the rules
# modules duplicate small constants rather than import each other. That
# convention's stated reason is the `{app_name}` placeholder breaking
# ABSOLUTE imports — which a relative import sidesteps. Duplicating a
# two-value range (rlms's MIN_GRADE/MAX_GRADE) is cheap; duplicating spec
# validation would mean the desk form and the API could disagree about
# whether a spec is publishable, and the spec is what somebody's money runs.
from ...tenant.rforex import strategy_spec as spec_rules


def _canonical(spec):
    """Key-sorted, whitespace-free JSON — so the checksum is a function of
    the spec's meaning, not of how the admin form happened to format it."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


class ForexStrategyVersion(Document):
    def validate(self):
        self._validate_version_number()
        parsed = self._validate_spec()
        self._enforce_immutability(parsed)
        self._validate_status_change()
        self.spec_checksum = hashlib.sha256(
            _canonical(parsed).encode("utf-8")
        ).hexdigest()

    def _validate_version_number(self):
        if not self.version or int(self.version) < 1:
            frappe.throw(_("Version must be a positive integer starting at 1."))
        clash = frappe.db.get_value(
            "Forex Strategy Version",
            {
                "strategy": self.strategy,
                "version": self.version,
                "name": ("!=", self.name or ""),
            },
            "name",
        )
        if clash:
            frappe.throw(
                _(
                    "Version {0} already exists for this strategy. Version "
                    "numbers are never reused — a user's pin is this number."
                ).format(self.version)
            )

    def _validate_spec(self):
        try:
            parsed = json.loads(self.spec or "")
        except ValueError as exc:
            frappe.throw(_("Spec is not valid JSON: {0}").format(exc))
        errors = spec_rules.validate_spec(parsed)
        if errors:
            frappe.throw(
                _("This spec cannot be published:") + "<br>" + "<br>".join(errors)
            )
        return parsed

    def _enforce_immutability(self, parsed):
        if self.is_new():
            return
        previous_status = self.get_db_value("status")
        if spec_rules.is_editable(previous_status):
            return
        if self.has_value_changed("spec"):
            # Compare meaning, not text: a reformat is not a change, but
            # anything that moves the checksum is.
            old_checksum = self.get_db_value("spec_checksum")
            new_checksum = hashlib.sha256(
                _canonical(parsed).encode("utf-8")
            ).hexdigest()
            if old_checksum and old_checksum != new_checksum:
                frappe.throw(
                    _(
                        "This version is {0} and its spec is frozen. Publish a "
                        "new version instead — users move to it by choice."
                    ).format(previous_status)
                )

    def _validate_status_change(self):
        if self.is_new():
            if self.status not in (spec_rules.STATUS_DRAFT, spec_rules.STATUS_PUBLISHED):
                frappe.throw(_("A new version starts as draft or published."))
            if self.status == spec_rules.STATUS_PUBLISHED:
                self.published_on = now_datetime()
            return

        previous = self.get_db_value("status")
        if previous == self.status:
            return
        if not spec_rules.can_transition(previous, self.status):
            frappe.throw(
                _("A version cannot move from {0} to {1}.").format(
                    previous, self.status
                )
            )
        if self.status == spec_rules.STATUS_BLOCKED:
            if not (self.blocked_reason or "").strip():
                frappe.throw(
                    _(
                        "Blocking stops every bot running this version. Give a "
                        "reason — it is shown to each user it stops."
                    )
                )
            self.blocked_on = now_datetime()
        elif self.status == spec_rules.STATUS_PUBLISHED and not self.published_on:
            self.published_on = now_datetime()
