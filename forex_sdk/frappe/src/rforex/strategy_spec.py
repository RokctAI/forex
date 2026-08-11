# Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
# For license information, please see license.txt

"""Strategy specs, versions and the run/stop verdict — frappe-free pure
module.

**Strategy is data, not code.** A `Forex Strategy` names a family; a
`Forex Strategy Version` carries one immutable spec — the parameter set a
bot reads to know what to do. Publishing a version freezes it. Changing a
published strategy means publishing a NEW version, and every user stays on
the version they pinned until they choose otherwise.

That choice has one exception, and it is the reason a status field exists at
all: **a version can be blocked, and a blocked version stops the bot.** The
alternative — silently migrating a blocked user onto the next version — is
worse than stopping: it would change what someone's real money is doing
without them asking, and it would do it precisely at the moment we've
decided the thing they signed up for is unsafe. So blocking stops. Restarting
is a user action, on a version they picked.

Every judgement here is a pure function over dicts. The API files own
reading rows and writing them; nothing in this module imports frappe.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

# --- Version lifecycle -----------------------------------------------------

STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_RETIRED = "retired"
STATUS_BLOCKED = "blocked"

STATUSES = (STATUS_DRAFT, STATUS_PUBLISHED, STATUS_RETIRED, STATUS_BLOCKED)

# Only a draft may be edited. Once a version is published, somebody's money
# may be running it, so the spec is frozen for good — including after it is
# retired or blocked (a blocked version must stay readable exactly as it was
# when it was blocked, or the post-mortem has nothing to read).
_EDITABLE_STATUSES = (STATUS_DRAFT,)

# Allowed status moves. Note what is absent: nothing returns to draft, and
# nothing reaches published except from draft or from blocked (an unblock).
_TRANSITIONS = {
    STATUS_DRAFT: (STATUS_PUBLISHED, STATUS_RETIRED),
    # Retiring stops OFFERING a version; it does not stop anybody running it.
    STATUS_PUBLISHED: (STATUS_RETIRED, STATUS_BLOCKED),
    # A retired version must still be blockable — grandfathered users are
    # exactly the people a safety block needs to reach.
    STATUS_RETIRED: (STATUS_BLOCKED, STATUS_PUBLISHED),
    # Unblocking after a fix is a re-publish of the same frozen spec.
    STATUS_BLOCKED: (STATUS_PUBLISHED, STATUS_RETIRED),
}

# --- Run verdicts ----------------------------------------------------------

RUN = "run"
STOP_UNASSIGNED = "stop_unassigned"
STOP_BLOCKED = "stop_blocked"
STOP_NOT_RUNNABLE = "stop_not_runnable"
STOP_PAUSED = "stop_paused"


def is_editable(status: Optional[str]) -> bool:
    """Whether a version's spec may still be written to."""
    return status in _EDITABLE_STATUSES


def can_transition(old: Optional[str], new: Optional[str]) -> bool:
    """Whether a status change is allowed. Unknown statuses on either side
    are refused rather than waved through."""
    if old not in _TRANSITIONS or new not in STATUSES:
        return False
    return new in _TRANSITIONS[old]


def is_runnable(status: Optional[str]) -> bool:
    """Whether a bot may run this version's spec at all.

    Retired counts as runnable: retirement removes a version from the
    catalog for NEW pins, and pulling the rug out from under everybody
    already on it would be an upgrade forced by the back office — the thing
    versioning exists to prevent. Only a block does that, and a block is a
    safety decision, not a housekeeping one.
    """
    return status in (STATUS_PUBLISHED, STATUS_RETIRED)


def assignment_verdict(
    assignment: Optional[Mapping[str, Any]],
    version: Optional[Mapping[str, Any]],
) -> str:
    """The one decision the strategy-serving endpoint applies: does this
    user's bot run right now?

    [assignment] is the user's `Forex User Strategy` row (or None when they
    have never pinned one); [version] is the `Forex Strategy Version` row it
    points at (or None when the pin dangles).

    Order matters. The block check comes FIRST — before the user's own
    active flag, before anything — because a blocked version must stop
    regardless of what any other row says. Everything else fails closed:
    an unknown status is not runnable.
    """
    if not isinstance(assignment, Mapping):
        return STOP_UNASSIGNED
    status = None
    if isinstance(version, Mapping):
        status = version.get("status")
    if status == STATUS_BLOCKED:
        return STOP_BLOCKED
    if version is None or not isinstance(version, Mapping):
        # A pin pointing at a version that no longer exists is not a reason
        # to fall forward onto the latest one.
        return STOP_UNASSIGNED
    if not is_runnable(status):
        return STOP_NOT_RUNNABLE
    if not assignment.get("active"):
        return STOP_PAUSED
    return RUN


# --- Version selection -----------------------------------------------------


def _version_number(row: Mapping[str, Any]) -> int:
    """A row's version number, or 0 when it is missing or unparseable — an
    unnumbered row sorts below every real one and can never be chosen as
    'latest'."""
    value = row.get("version")
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def compare_versions(left: Any, right: Any) -> int:
    """-1 / 0 / 1 for left older / same / newer. Unparseable version
    numbers compare as 0, which sorts them below every real version rather
    than above it."""
    a = _version_number({"version": left})
    b = _version_number({"version": right})
    return (a > b) - (a < b)


def latest_publishable(versions: Sequence[Mapping[str, Any]]) -> Optional[Mapping]:
    """The highest-numbered version a NEW user may be offered.

    Only `published` — a retired version is still legal to run but is no
    longer on the shelf, and a blocked one is on fire.
    """
    candidates = [
        v
        for v in versions
        if isinstance(v, Mapping)
        and v.get("status") == STATUS_PUBLISHED
        and _version_number(v) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=_version_number)


def upgrade_offer(
    pinned_version: Any, versions: Sequence[Mapping[str, Any]]
) -> Optional[int]:
    """The version number to OFFER as an upgrade, or None when there is
    nothing to offer.

    An offer, never an action: the user's bot keeps running what it is
    running until they accept. Returns None when the pinned version is
    already the newest published one — and, deliberately, when the only
    newer versions are retired or blocked.
    """
    latest = latest_publishable(versions)
    if latest is None:
        return None
    newest = _version_number(latest)
    if compare_versions(newest, pinned_version) <= 0:
        return None
    return newest


# --- Spec validation -------------------------------------------------------

# The only spec shape implemented today, mirroring the London breakout cBot's
# parameters (src/LondonBreakout.Core). A spec with any other `kind` is
# refused rather than half-validated: an unrecognised kind means a bot on the
# other end would be reading fields nobody here checked.
KIND_SESSION_BREAKOUT = "session_breakout"
SUPPORTED_KINDS = (KIND_SESSION_BREAKOUT,)

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

DISTANCE_MODE_PIPS = "pips"
DISTANCE_MODE_ATR = "atr_multiple"
DISTANCE_MODES = (DISTANCE_MODE_PIPS, DISTANCE_MODE_ATR)

STOP_MODE_OPPOSITE = "opposite_range_side"
STOP_MODES = (STOP_MODE_OPPOSITE, DISTANCE_MODE_PIPS, DISTANCE_MODE_ATR)

_REQUIRED_KEYS = (
    "kind",
    "symbol",
    "session_timezone",
    "range_start",
    "signal",
    "trading_days",
    "entry_buffer",
    "stop",
    "target_r",
)


def _parse_hhmm(value: Any) -> Optional[int]:
    """"HH:MM" as minutes past midnight, or None when it isn't one."""
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _validate_distance(label: str, value: Any, modes: Sequence[str]) -> List[str]:
    errors: List[str] = []
    if not isinstance(value, Mapping):
        return ["{0} must be an object with a mode and a value.".format(label)]
    mode = value.get("mode")
    if mode not in modes:
        errors.append(
            "{0}.mode must be one of {1}; got {2!r}.".format(
                label, ", ".join(modes), mode
            )
        )
        return errors
    if mode == STOP_MODE_OPPOSITE:
        # The opposite side of the range is a derived level, not a distance.
        return errors
    number = value.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        errors.append("{0}.value must be a number.".format(label))
    elif number != number or number <= 0:
        errors.append("{0}.value must be greater than zero.".format(label))
    return errors


def validate_spec(spec: Any) -> List[str]:
    """Every problem with a spec, as human-readable strings. Empty list =
    valid.

    Returning ALL the errors rather than throwing on the first one is
    deliberate: a spec is authored by a person in an admin form, and telling
    them about one mistake at a time across four save attempts is how
    half-corrected specs get published.
    """
    errors: List[str] = []
    if not isinstance(spec, Mapping):
        return ["A strategy spec must be an object."]

    for key in _REQUIRED_KEYS:
        if key not in spec:
            errors.append("Missing required key: {0}.".format(key))

    kind = spec.get("kind")
    if "kind" in spec and kind not in SUPPORTED_KINDS:
        errors.append(
            "Unsupported kind {0!r}; this build knows only: {1}.".format(
                kind, ", ".join(SUPPORTED_KINDS)
            )
        )

    symbol = spec.get("symbol")
    if "symbol" in spec and (not isinstance(symbol, str) or not symbol.strip()):
        errors.append("symbol must be a non-empty string.")

    tz = spec.get("session_timezone")
    if "session_timezone" in spec and (not isinstance(tz, str) or "/" not in tz):
        # Not a full IANA lookup (that would need a tz database and this
        # module stays dependency-free) — just enough to reject "GMT+2",
        # which is the mistake that silently breaks DST.
        errors.append(
            "session_timezone must be an IANA zone name such as "
            "'Europe/London', not a fixed offset."
        )

    start = _parse_hhmm(spec.get("range_start"))
    signal = _parse_hhmm(spec.get("signal"))
    if "range_start" in spec and start is None:
        errors.append("range_start must be a 'HH:MM' time.")
    if "signal" in spec and signal is None:
        errors.append("signal must be a 'HH:MM' time.")
    if start is not None and signal is not None and start >= signal:
        # The overnight-wrap limitation, stated where it bites. This is the
        # open range-start question in the bot's README: answering it with
        # the broker daily boundary (17:00 New York = 22:00/23:00 London,
        # the previous day) needs a range that wraps past midnight, which
        # neither the cBot nor this spec supports yet. Refusing loudly beats
        # accepting a spec the runtime would silently mis-measure.
        errors.append(
            "range_start must be earlier in the day than signal. Overnight "
            "ranges that wrap past midnight are not supported yet — see the "
            "open range-start question in src/LondonBreakout/README.md."
        )

    days = spec.get("trading_days")
    if "trading_days" in spec:
        if not isinstance(days, (list, tuple)) or not days:
            errors.append("trading_days must be a non-empty list of day names.")
        else:
            unknown = [d for d in days if d not in DAY_NAMES]
            if unknown:
                errors.append(
                    "Unknown trading_days entries: {0}. Use {1}.".format(
                        ", ".join(repr(d) for d in unknown), ", ".join(DAY_NAMES)
                    )
                )

    if "entry_buffer" in spec:
        errors.extend(
            _validate_distance("entry_buffer", spec.get("entry_buffer"), DISTANCE_MODES)
        )
    if "stop" in spec:
        errors.extend(_validate_distance("stop", spec.get("stop"), STOP_MODES))
    if "min_range" in spec:
        errors.extend(
            _validate_distance("min_range", spec.get("min_range"), DISTANCE_MODES)
        )

    target = spec.get("target_r")
    if "target_r" in spec:
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            errors.append("target_r must be a number.")
        elif target != target or target <= 0:
            errors.append("target_r must be greater than zero.")

    return errors


def is_valid_spec(spec: Any) -> bool:
    """Convenience over [validate_spec] for callers that only branch."""
    return not validate_spec(spec)


def public_version_view(version: Mapping[str, Any]) -> Dict[str, Any]:
    """The catalog-safe view of a version row: what it is and whether it can
    run, with no spec. The spec itself is served only by the gated endpoint,
    so an unentitled caller cannot read the parameters out of a listing."""
    status = version.get("status")
    return {
        "version": _version_number(version),
        "status": status,
        "runnable": is_runnable(status),
        "blocked": status == STATUS_BLOCKED,
        "blocked_reason": version.get("blocked_reason")
        if status == STATUS_BLOCKED
        else None,
    }
