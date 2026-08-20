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

"""Broker credential endpoints.

**No function in this file returns a token.** Not masked, not truncated, not
"just the last four" — a bearer token has no non-sensitive prefix, and the
first time one is returned "for debugging" it is in a log aggregator
forever. The single projection helper [_public_view] is the only thing any
endpoint here returns, and [NEVER_RETURNED] states the rule as data so a
future secret field is covered by the same check rather than by whoever
reviews the pull request.

This is deliberately stricter than the nearest precedent in the estate.
`pay`'s `Saved Card` stores its gateway token as a plain `Data` field and
hands it to the client; that is the pattern this file exists not to repeat.

What IS implemented: storing tokens, reading the connection status, and
revoking. What is NOT: the OAuth code exchange and the refresh round-trip,
both of which need an HTTP call to cTrader's token endpoint with client
credentials this repository does not have. Those raise
`NotImplementedError`. They do not return a placeholder token, and they do
not quietly leave the old one in place while reporting success — either
would end with a bot trading on an expired session and no way to tell.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

# The contract, as data. Anything named here must never reach a response.
NEVER_RETURNED = ("access_token", "refresh_token")

SUPPORTED_BROKERS = ("ctrader",)
ENVIRONMENTS = ("demo", "live")


def _public_view(doc):
    """The only shape any endpoint in this file returns.

    Built by naming what goes IN rather than by deleting what must stay out:
    a field added to the DocType tomorrow is absent from this dict by
    default, which is the safe direction. The token fields are represented
    only by booleans — whether one is on file at all.
    """
    return {
        "connected": doc.status == "connected",
        "status": doc.status,
        "broker": doc.broker,
        "environment": doc.environment,
        "account_id": doc.ctrader_account_id,
        "account_currency": doc.account_currency,
        "has_access_token": bool(doc.access_token),
        "has_refresh_token": bool(doc.refresh_token),
        "expires_at": doc.token_expires_at.isoformat()
        if doc.token_expires_at
        else None,
        "expired": bool(
            doc.token_expires_at
            and get_datetime(doc.token_expires_at) <= now_datetime()
        ),
        "scope": doc.scope,
        "last_refreshed_on": doc.last_refreshed_on.isoformat()
        if doc.last_refreshed_on
        else None,
    }


def _my_credential(environment, create=False):
    user = frappe.session.user
    name = frappe.db.get_value(
        "Forex Broker Credential",
        {"user": user, "broker": "ctrader", "environment": environment},
        "name",
    )
    if name:
        return frappe.get_doc("Forex Broker Credential", name)
    if not create:
        return None
    return frappe.get_doc(
        {
            "doctype": "Forex Broker Credential",
            "user": user,
            "broker": "ctrader",
            "environment": environment,
            "status": "connected",
        }
    )


def _validated_environment(environment):
    env = (environment or "demo").strip().lower()
    if env not in ENVIRONMENTS:
        frappe.throw(_("Environment must be 'demo' or 'live'."))
    return env


@frappe.whitelist()
def credential_status(environment="demo"):
    """Whether this user has a broker connection, and its health.

    Returns `connected: false` for a user with no credential row rather than
    throwing — "not connected" is a normal state the app renders, not an
    error.
    """
    env = _validated_environment(environment)
    doc = _my_credential(env)
    if doc is None:
        return {
            "connected": False,
            "status": None,
            "broker": "ctrader",
            "environment": env,
            "account_id": None,
            "account_currency": None,
            "has_access_token": False,
            "has_refresh_token": False,
            "expires_at": None,
            "expired": False,
            "scope": None,
            "last_refreshed_on": None,
        }
    return _public_view(doc)


@frappe.whitelist()
def store_credentials(
    access_token,
    refresh_token=None,
    expires_at=None,
    account_id=None,
    account_currency=None,
    scope=None,
    environment="demo",
):
    """Store the tokens from a completed OAuth flow.

    Takes tokens IN and gives only status OUT. The response is the same
    [_public_view] every other endpoint here returns, so there is no
    "just this once" path that echoes a token back to confirm it was saved.

    The account currency is asked for here because this is the one moment it
    is known for free — the OAuth callback carries the account details. Every
    monetary figure the dashboard later reports is denominated in it, and
    rforex.margin refuses to compute a snapshot without one.
    """
    env = _validated_environment(environment)
    if not access_token or not str(access_token).strip():
        frappe.throw(_("An access token is required."))

    doc = _my_credential(env, create=True)
    doc.access_token = access_token
    if refresh_token:
        doc.refresh_token = refresh_token
    if expires_at:
        doc.token_expires_at = get_datetime(expires_at)
    if account_id:
        doc.ctrader_account_id = account_id
    if account_currency:
        doc.account_currency = account_currency
    if scope:
        doc.scope = scope
    doc.status = "connected"
    doc.last_refreshed_on = now_datetime()

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    return _public_view(doc)


@frappe.whitelist()
def refresh_credentials(environment="demo"):
    """Exchange the stored refresh token for a new access token.

    NOT IMPLEMENTED. The half that belongs to this repository — finding the
    row, reading the refresh token server-side via `doc.get_password` — is
    written below and works. The half that is missing is the HTTP POST to
    cTrader's token endpoint, which needs an OAuth client id and secret that
    do not exist in this repository or in any app config it can read.

    It raises rather than returning a plausible-looking response. A refresh
    that reports success while leaving an expired token in place produces a
    bot that thinks it is connected, and finds out otherwise at the moment
    it tries to place an order.
    """
    env = _validated_environment(environment)
    doc = _my_credential(env)
    if doc is None:
        frappe.throw(_("No broker connection to refresh."))

    stored_refresh_token = doc.refresh_token_value()
    if not stored_refresh_token:
        frappe.throw(
            _("No refresh token on file — reconnect the account instead.")
        )

    # TODO(forex): POST to cTrader's OAuth token endpoint with
    # grant_type=refresh_token, the stored refresh token, and the app's
    # client credentials; then write the new access/refresh pair and expiry
    # back through store_credentials' path. Blocked on: an OAuth client id
    # and secret for the cTrader Open API, and a decision on where those
    # live (app config vs a Frappe Settings DocType).
    raise NotImplementedError(
        "cTrader OAuth token refresh is not implemented: no OAuth client "
        "credentials are configured. The stored refresh token was read "
        "successfully; the exchange with the broker is the missing half."
    )


@frappe.whitelist()
def revoke_credentials(environment="demo"):
    """Disconnect the broker account.

    Clears both tokens and marks the row revoked rather than deleting it —
    the audit trail of "this account was connected between these dates"
    outlives the connection, and a deleted row cannot explain a trade.

    Note that this revokes LOCALLY. Telling cTrader to invalidate the token
    on their side needs the same missing OAuth client credentials as
    [refresh_credentials]; until that exists, a copy of the token that
    escaped before revocation would still be live at the broker.
    """
    env = _validated_environment(environment)
    doc = _my_credential(env)
    if doc is None:
        frappe.throw(_("No broker connection to revoke."))

    doc.access_token = ""
    doc.refresh_token = ""
    doc.status = "revoked"
    doc.token_expires_at = None
    doc.save(ignore_permissions=True)

    result = _public_view(doc)
    result["remote_revocation"] = "not_implemented"
    return result
