# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""Account dashboard: balance, open positions, history, and the derived
equity and margin level.

**Read this before adding a fallback.** Every number this file returns is
one a person looks at before deciding how much to risk, and one the risk
layer divides by. A wrong balance here is a wrong position size there. So
there is exactly one rule, and it has no exceptions:

    If the broker figures are not available, this raises. It does not
    return zeros, it does not return the last known values without saying
    so, and it does not return a shape with the numbers omitted and a
    `success: true` beside it.

Right now the broker figures are NEVER available, because no cTrader Open
API client exists in this repository. [_broker_snapshot] therefore raises
`NotImplementedError` on every call, and so does everything that depends on
it. That is the honest state of this endpoint and it is meant to be visible:
a dashboard that renders an error is a nuisance, a dashboard that renders a
confident fabricated equity is how an account gets sized off a number nobody
computed.

The arithmetic itself is real, tested and finished — rforex.margin, 39 unit
tests. The assembly below is written against it so that when the connector
lands, [_broker_snapshot] is the only function that changes.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from .. import margin
from . import credential as credential_api


def _broker_snapshot(user, environment):
    """Live account figures from the broker.

    NOT IMPLEMENTED. Must return a dict of:

        balance          — cash balance, in the account currency
        used_margin      — margin currently tied up by open positions
        positions        — [{id, symbol, side, volume, unrealised_pl,
                             currency, opened_at}, ...]
        account_currency — ISO 4217 code, from the broker, not guessed
        as_of            — datetime the broker stated these were true at

    Blocked on: a cTrader Open API client (protobuf over TLS, or the REST
    surface where it covers what is needed), plus the OAuth client
    credentials that api/credential.refresh_credentials is also waiting on.

    This raises rather than returning a stub because the caller cannot tell
    a stub from a reading. Every alternative considered — zeros, last-known
    values, a partially-filled dict — produces a dashboard that looks like
    it is working.
    """
    raise NotImplementedError(
        "No cTrader Open API client exists yet, so live account figures "
        "cannot be read. This endpoint deliberately fails rather than "
        "returning placeholder balances: a fabricated equity becomes a real "
        "position size. See forex_sdk/README.md."
    )


def _broker_history(user, environment, limit):
    """Closed-position history from the broker.

    NOT IMPLEMENTED, and blocked on the same missing client as
    [_broker_snapshot]. Must return closed trades with, per row, the
    realised amount AND the currency it is denominated in — a realised P/L
    stored without its currency cannot be reconstructed later.
    """
    raise NotImplementedError(
        "No cTrader Open API client exists yet, so trade history cannot be "
        "read. See forex_sdk/README.md."
    )


@frappe.whitelist()
def dashboard(environment="demo"):
    """The account dashboard payload: balance, positions, computed equity
    and margin level, with the freshness of the underlying reading.

    Raises `NotImplementedError` today — see [_broker_snapshot]. The
    assembly below is the finished shape and runs unchanged once the
    connector exists.

    Note `stale` and `as_of` in the response. Margin level moves on every
    tick; a number shown without the time it was true at is only marginally
    better than a made-up one, and the client is expected to render the
    staleness rather than hide it.
    """
    user = frappe.session.user
    status = credential_api.credential_status(environment)
    if not status["connected"]:
        # A user with no broker connected is a normal state, not an error —
        # and notably NOT an account with a zero balance.
        return {
            "connected": False,
            "reason": "no_broker_connection",
            "snapshot": None,
            "positions": [],
        }

    reading = _broker_snapshot(user, environment)

    snapshot = margin.snapshot(
        balance=reading["balance"],
        used_margin=reading["used_margin"],
        positions=reading["positions"],
        account_currency=reading["account_currency"],
        as_of=reading["as_of"],
        now=now_datetime(),
    )

    return {
        "connected": True,
        "environment": environment,
        "account_id": status["account_id"],
        "snapshot": snapshot,
        "positions": [
            {
                "id": p.get("id"),
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "volume": p.get("volume"),
                "unrealised_pl": p.get("unrealised_pl"),
                # The currency travels with every amount, per position, not
                # once at the top of the payload — a client rendering a row
                # must not have to reach elsewhere to know what the number is.
                "currency": p.get("currency"),
                "opened_at": p.get("opened_at"),
            }
            for p in reading["positions"]
        ],
    }


@frappe.whitelist()
def history(environment="demo", limit=50):
    """Closed-trade history.

    Raises `NotImplementedError` today — see [_broker_history].
    """
    user = frappe.session.user
    status = credential_api.credential_status(environment)
    if not status["connected"]:
        return {"connected": False, "reason": "no_broker_connection", "trades": []}
    return {
        "connected": True,
        "trades": _broker_history(user, environment, int(limit)),
    }


@frappe.whitelist()
def margin_thresholds():
    """The margin-level bands the dashboard colours against.

    Served rather than duplicated in the client so the two cannot drift —
    a UI showing "healthy" at a level the server calls a margin call is
    worse than showing nothing.

    These are conventional retail-broker defaults, NOT this user's broker's
    actual values; the real numbers are account-specific and arrive with the
    connector. Labelled `source: "defaults"` so the client can say so.
    """
    return {
        "source": "defaults",
        "stop_out_pct": margin.STOP_OUT_LEVEL_PCT,
        "margin_call_pct": margin.MARGIN_CALL_LEVEL_PCT,
        "warning_pct": margin.WARNING_LEVEL_PCT,
        "max_snapshot_age_seconds": int(margin.MAX_SNAPSHOT_AGE.total_seconds()),
    }
