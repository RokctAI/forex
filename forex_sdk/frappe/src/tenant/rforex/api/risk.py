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

"""Risk profile endpoints.

A fifth api module beyond the four the SDK brief named, because the risk
picker needs somewhere to save to and none of the other four is the right
home: risk is not entitlement (it is not about what you paid for), not
account (it is not read from the broker), and not strategy (it outlives any
single strategy pin).

The one decision these endpoints implement: **a preset is resolved to
parameters at the moment the user picks it, and those parameters are what
is stored.** The preset name is kept as a label only. See
rforex.risk_presets for why — in short, storing the name would mean a later
edit to the preset table silently re-risked every account that had ever
chosen it.

Consequently `set_preset` takes a NAME and stores NUMBERS, and
`my_risk_profile` returns the numbers rather than the name. A client that
only ever read the name back would be reading a label, not its limits.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from .. import risk_presets


def _my_profile(user):
    name = frappe.db.get_value("Forex Risk Profile", {"user": user}, "name")
    return frappe.get_doc("Forex Risk Profile", name) if name else None


def _view(doc):
    """The resolved parameters, re-resolved through risk_presets on the way
    out.

    Re-resolving on read is not redundant: it applies the ceilings and the
    per-field conservative fallback to whatever is actually in the row, so a
    profile corrupted by a bad migration or a direct database edit cannot
    hand the client wider limits than the rules allow.
    """
    stored = None
    if doc is not None:
        stored = {
            name: doc.get(name) for name in risk_presets.PARAMETER_NAMES
        }
    resolved = risk_presets.resolve_stored(stored)
    return {
        # A record of what was picked, for display. Nothing decides on it.
        "preset": doc.preset if doc else None,
        "resolved_on": doc.resolved_on.isoformat()
        if doc and doc.resolved_on
        else None,
        "account_currency": doc.account_currency if doc else None,
        # The truth.
        "risk_profile": resolved,
        # Whether these are the user's own stored numbers or the safe
        # default they get for having none. The UI says so — a user running
        # on the fallback should know they never chose it.
        "is_default": doc is None,
    }


@frappe.whitelist()
def my_risk_profile():
    """The caller's resolved risk parameters.

    A user with no profile gets the most conservative parameters and
    `is_default: true` — never an empty response the client would have to
    invent limits for.
    """
    return _view(_my_profile(frappe.session.user))


@frappe.whitelist()
def available_presets():
    """The selectable presets and the parameters each resolves to.

    Served rather than hardcoded in the client so the picker's displayed
    consequence and the stored result cannot disagree. Ordered tightest
    first.
    """
    return [
        {"name": name, "parameters": risk_presets.resolve(name)}
        for name in risk_presets.preset_names()
    ]


@frappe.whitelist()
def set_preset(preset, account_currency=None):
    """Resolve a preset name to parameters and store the parameters.

    An unknown name is refused rather than quietly resolved to the
    conservative floor. The fallback-to-tightest rule is for ABSENCE — a
    missing row, a corrupt field, an unavailable adapter. An explicit
    request naming a preset that does not exist is a client bug, and
    silently storing something the user did not ask for would hide it.
    """
    name = (preset or "").strip().lower()
    if name not in risk_presets.PRESETS:
        frappe.throw(
            _("Unknown risk preset {0}. Choose one of: {1}.").format(
                preset, ", ".join(risk_presets.preset_names())
            )
        )

    resolved = risk_presets.resolve(name)
    user = frappe.session.user
    doc = _my_profile(user)
    if doc is None:
        doc = frappe.get_doc({"doctype": "Forex Risk Profile", "user": user})

    doc.preset = name
    for field, value in resolved.items():
        doc.set(field, value)
    doc.resolved_on = now_datetime()
    if account_currency:
        doc.account_currency = account_currency

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    return _view(doc)
