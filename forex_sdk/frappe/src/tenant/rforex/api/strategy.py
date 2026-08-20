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

"""Strategy catalog and spec serving.

The split that matters:

- **Listing is free.** Anyone may see what strategies exist, what they claim
  to do and which tier they need. A paywall nobody can see the inside of
  does not sell anything, and none of that metadata is the product.
- **The spec is the product, and it is gated here.** `get_strategy` is the
  real enforcement point — not `my_entitlements`, which only explains, and
  not the client, which cannot be trusted to hold a lock it can see. The
  `Forex Strategy Version` DocType grants no read permission below System
  Manager precisely so the generic resource API cannot route around this.

Blocked versions are handled in one place — rforex.strategy_spec — and the
answer is always STOP, never "quietly move them to the next version".
"""

import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from .. import entitlements, strategy_spec
from . import entitlement as entitlement_api


def _versions_of(strategy_name):
    return frappe.get_all(
        "Forex Strategy Version",
        filters={"strategy": strategy_name},
        fields=["name", "version", "status", "blocked_reason", "notes", "published_on"],
        ignore_permissions=True,
    )


def _my_assignment(user, strategy_name):
    rows = frappe.get_all(
        "Forex User Strategy",
        filters={"user": user, "strategy": strategy_name},
        fields=["name", "pinned_version", "risk_profile", "active"],
        ignore_permissions=True,
        limit=1,
    )
    return rows[0] if rows else None


@frappe.whitelist(allow_guest=True)
def list_strategies():
    """The public catalog: what exists, what it needs, and whether the
    caller can run it.

    Guest-allowed on purpose — the pre-signup browse is the funnel. A guest
    session has no periods, so every `verdict` comes back `needs_active`,
    which is the correct thing to show them.

    Carries no spec. `latest_version` is the newest PUBLISHED version, which
    is what a new user would pin; a strategy whose only versions are drafts
    reports null and is not offerable.
    """
    user = frappe.session.user
    periods = entitlement_api.get_periods(user) if user != "Guest" else []
    today = getdate(nowdate())

    out = []
    for strategy in frappe.get_all(
        "Forex Strategy",
        filters={"enabled": 1},
        fields=["name", "strategy_key", "title", "summary", "min_tier"],
        ignore_permissions=True,
    ):
        versions = _versions_of(strategy.name)
        latest = strategy_spec.latest_publishable(versions)
        out.append(
            {
                "key": strategy.strategy_key,
                "title": strategy.title,
                "summary": strategy.summary,
                "min_tier": strategy.min_tier or entitlements.TIER_STANDARD,
                "latest_version": latest["version"] if latest else None,
                "offerable": latest is not None,
                "verdict": entitlements.strategy_verdict(
                    periods, today, strategy.min_tier
                ),
            }
        )
    return out


@frappe.whitelist()
def get_strategy(key):
    """One strategy with the spec the caller is entitled to run.

    The gate is applied here, before the spec is read, and the deny answers
    are distinguishable so the UI can say the right thing:
    `needs_active` sells a subscription, `needs_upgrade` sells an upgrade to
    somebody who already pays.

    Which spec is served:
    - the caller's PINNED version, when they have one — including when a
      newer version exists, because upgrades are opt-in;
    - otherwise the latest published version, as a preview of what pinning
      would give them.

    A blocked pinned version returns no spec at all, with `run_verdict` =
    `stop_blocked` and the reason. This is the force-stop: the bot is told
    to stop, and is NOT handed the next version's spec instead.
    """
    user = frappe.session.user
    strategy = frappe.db.get_value(
        "Forex Strategy",
        {"strategy_key": key, "enabled": 1},
        ["name", "strategy_key", "title", "summary", "min_tier"],
        as_dict=True,
    )
    if not strategy:
        frappe.throw(_("No such strategy."), frappe.DoesNotExistError)

    periods = entitlement_api.get_periods(user)
    today = getdate(nowdate())
    verdict = entitlements.strategy_verdict(periods, today, strategy.min_tier)
    if verdict != entitlements.ALLOWED:
        # No spec in the payload, and no partial spec either.
        frappe.throw(
            _("A subscription is required to run this strategy.")
            if verdict == entitlements.NEEDS_ACTIVE
            else _("This strategy needs a higher subscription tier."),
            frappe.PermissionError,
        )

    versions = _versions_of(strategy.name)
    assignment = _my_assignment(user, strategy.name)

    pinned = None
    if assignment and assignment.get("pinned_version"):
        pinned = next(
            (v for v in versions if v["name"] == assignment["pinned_version"]), None
        )

    serving = pinned or strategy_spec.latest_publishable(versions)
    run_verdict = strategy_spec.assignment_verdict(assignment, pinned)

    if assignment:
        frappe.get_doc("Forex User Strategy", assignment["name"]).record_verdict(
            run_verdict
        )

    payload = {
        "key": strategy.strategy_key,
        "title": strategy.title,
        "summary": strategy.summary,
        "min_tier": strategy.min_tier,
        "pinned_version": pinned["version"] if pinned else None,
        "run_verdict": run_verdict,
        "upgrade_available": strategy_spec.upgrade_offer(
            pinned["version"] if pinned else 0, versions
        ),
        "versions": [strategy_spec.public_version_view(v) for v in versions],
        "spec": None,
        "spec_checksum": None,
        "blocked_reason": None,
    }

    if run_verdict == strategy_spec.STOP_BLOCKED:
        payload["blocked_reason"] = pinned.get("blocked_reason")
        return payload

    if serving is not None and strategy_spec.is_runnable(serving.get("status")):
        row = frappe.db.get_value(
            "Forex Strategy Version",
            serving["name"],
            ["spec", "spec_checksum"],
            as_dict=True,
        )
        payload["spec"] = json.loads(row.spec)
        payload["spec_checksum"] = row.spec_checksum
        payload["serving_version"] = serving["version"]

    return payload


@frappe.whitelist()
def pin_version(key, version):
    """Move the caller onto a specific version of a strategy — the opt-in
    half of the upgrade rule. Always an explicit user action; nothing else
    writes this.

    Refuses to pin a version that is not runnable, so a user cannot opt into
    a blocked one and cannot pin a draft.
    """
    user = frappe.session.user
    strategy = frappe.db.get_value(
        "Forex Strategy", {"strategy_key": key, "enabled": 1}, "name"
    )
    if not strategy:
        frappe.throw(_("No such strategy."), frappe.DoesNotExistError)

    periods = entitlement_api.get_periods(user)
    min_tier = frappe.db.get_value("Forex Strategy", strategy, "min_tier")
    if entitlements.strategy_verdict(
        periods, getdate(nowdate()), min_tier
    ) != entitlements.ALLOWED:
        frappe.throw(
            _("A subscription is required to run this strategy."),
            frappe.PermissionError,
        )

    row = frappe.db.get_value(
        "Forex Strategy Version",
        {"strategy": strategy, "version": int(version)},
        ["name", "status"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("No such version."), frappe.DoesNotExistError)
    if row.status == strategy_spec.STATUS_BLOCKED:
        frappe.throw(
            _("That version is blocked and cannot be started.")
        )
    if not strategy_spec.is_runnable(row.status):
        frappe.throw(_("That version is not available to run."))

    existing = _my_assignment(user, strategy)
    if existing:
        doc = frappe.get_doc("Forex User Strategy", existing["name"])
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Forex User Strategy",
                "user": user,
                "strategy": strategy,
                "active": 0,
            }
        )
    doc.pinned_version = row.name
    doc.save(ignore_permissions=True)
    return {"pinned_version": int(version), "active": bool(doc.active)}


@frappe.whitelist()
def set_active(key, active):
    """The user's own run/pause switch.

    Turning it on is a request, not a guarantee: the serving endpoint still
    checks entitlement and the pinned version's status on every call, and a
    blocked version overrides this flag entirely.
    """
    user = frappe.session.user
    strategy = frappe.db.get_value("Forex Strategy", {"strategy_key": key}, "name")
    assignment = _my_assignment(user, strategy) if strategy else None
    if not assignment:
        frappe.throw(_("Pin a version before starting this strategy."))

    doc = frappe.get_doc("Forex User Strategy", assignment["name"])
    doc.active = 1 if frappe.parse_json(active) else 0
    doc.save(ignore_permissions=True)

    pinned = frappe.db.get_value(
        "Forex Strategy Version", doc.pinned_version, ["version", "status"], as_dict=True
    )
    verdict = strategy_spec.assignment_verdict(
        {"active": doc.active}, dict(pinned) if pinned else None
    )
    doc.record_verdict(verdict)
    return {"active": bool(doc.active), "run_verdict": verdict}
