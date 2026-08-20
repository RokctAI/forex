# forex_sdk

The app-and-backend half of this repository: a Rokct SDK pair (`dart/` + `frappe/`) that lets a
non-expert pick a strategy, pick a risk preset, connect a broker account, and watch it — while the
cBots in [`src/`](../src) do the trading.

This is a **skeleton**. It is laid out and wired to house conventions, the decisions are encoded and
unit-tested, and the parts that are not built say so out loud. Nothing here has traded anything.

---

## What is implemented

### `frappe/` — the `rforex` backend module

**Pure rule modules** (`src/tenant/rforex/`) — no `frappe` import, no site needed, `python -m unittest`:

| Module | What it decides |
|---|---|
| `risk_presets.py` | Preset name → four resolved parameters; ceilings; the fallback-to-tightest rule |
| `strategy_spec.py` | Spec validation, version comparison, status transitions, the run/stop verdict |
| `margin.py` | Equity, free margin, margin level, warning bands, snapshot freshness |
| `entitlements.py` | Subscription coverage, tiers, and the three-way allow / needs-active / needs-upgrade verdict |

**161 unit tests, all passing.** Run them with:

```bash
cd forex_sdk/frappe/src/tenant/rforex && python3 -m unittest discover -s tests -t .
```

They need no Frappe, no site and no database — each test loads its module by file path, matching
`agent/lms`'s `tests/test_*.py`.

**DocTypes** (`frappe/src/tenant/doctype/`): `Forex Strategy`, `Forex Strategy Version`, `Forex User Strategy`,
`Forex Risk Profile`, `Forex Broker Credential`, `Forex Subscription Period`.

**API** (`src/tenant/rforex/api/`): `strategy.py`, `account.py`, `credential.py`, `entitlement.py`,
`risk.py`. All fifteen whitelisted methods are declared in `manifest.json` and a test asserts the
manifest and the code agree in both directions.

### `dart/` — `forex_sdk`

Barrel, models, the four consumer-owned interfaces, DI with fail-closed stand-ins, an HTTP
repository, two screens (strategy list, risk preset), and the host route template.

---

## The decisions, and where they live

**Strategy is data, not code.** A `Forex Strategy` names a family; a `Forex Strategy Version` holds
one immutable spec. Publishing freezes it — `forex_strategy_version.py` refuses a spec edit once the
version leaves draft, comparing checksums so a reformat is not mistaken for a change.

**Users pin a version; upgrades are opt-in.** `Forex User Strategy.pinned_version` moves only when
the user accepts an offer. `upgrade_offer()` returns a number to show, never an action to take.

**Except that blocked force-stops.** Flipping a version to `blocked` stops every bot running it,
rather than migrating them to the next version. Migrating would change what somebody's money is
doing without them asking, at exactly the moment we have decided their choice is unsafe. The block
check is the *first* branch in `assignment_verdict()`, ahead of the user's own active flag, and a
block requires a reason because a bot that stops silently is indistinguishable from one that
crashed.

**Risk presets store resolved parameters.** `Forex Risk Profile` holds `risk_per_trade_pct`,
`daily_loss_pct`, `max_drawdown_pct` and `max_open_positions`; the preset name survives as a label
nothing reads. Redefining "balanced" next quarter therefore changes what new users get and nothing
about existing ones. A null/missing/corrupt value resolves to the **most conservative** setting —
per field, not just per row, so a half-written profile cannot leave one dimension open. That floor
is *derived* from the preset table rather than hardcoded, so adding a tighter preset moves it
automatically.

**Broker credentials never leave the server.** `access_token` and `refresh_token` are Frappe
`Password` fields (stored in `__Auth`, not in the DocType's table) at `permlevel: 1`, which puts
them outside the owner's own read permission. No whitelisted method returns them; `credential.py`
has one projection helper built by naming what goes *in*, and a test walks the api modules' return
statements to prove no token name appears in one. This is deliberately stricter than `pay`'s
`Saved Card`, which stores its token as plain `Data` and hands it to the client.

**Forex reads the wallet and never writes to it.** `ForexWalletBalanceSource` is one method wide.
The alternative — depending on `WalletRepositoryFacade` — would put `sendWalletBalance()` and
`walletTopUp()` within reach of every screen here, for the sake of reading one number.

**A currency code sits next to every amount.** `Money` cannot be constructed without one.
`rforex.margin` refuses to compute a snapshot without one and raises rather than summing across
currencies. `Forex Subscription Period.currency` is mandatory whenever `amount` is set. Nothing
upstream does this and it cannot be recovered later: an amount of 4,812.55 whose currency was never
recorded is not a value.

**Entitlement explains in one place and gates in another.** `my_entitlements` only describes locks
so the UI can say the right thing; the real gate is inside `get_strategy`, which is why
`Forex Strategy Version` grants no read permission below System Manager — otherwise the generic
resource API would route straight around it. `record_subscription_period` is
`frappe.only_for("System Manager")`.

---

## What is stubbed, and what that means

Everything in this list raises or returns a documented empty value. **Nothing returns fabricated
data.** That rule is strictest in the account path, where a made-up number becomes a real position
size.

| Thing | State | Blocked on |
|---|---|---|
| `api/account.py` `_broker_snapshot` | `NotImplementedError` | A cTrader Open API client |
| `api/account.py` `_broker_history` | `NotImplementedError` | Same |
| `api/credential.py` `refresh_credentials` | `NotImplementedError` after successfully reading the stored token | OAuth client id/secret, and a decision on where they live |
| `revoke_credentials` remote half | Local revoke works; returns `remote_revocation: "not_implemented"` | Same credentials |
| Dart account dashboard route | Renders an explicit "figures unavailable" screen | The backend above |
| Host adapters in `forex_route_pages.dart` | `TODO(host)`, each returning its fail-closed value | Real `subscriptions_sdk` / `wallet_sdk` / `payments_sdk` symbols |
| Strategy detail screen | Not built — a snackbar says so | Its centrepiece is the dashboard |

The margin arithmetic those stubs would feed is **finished and tested** — 39 unit tests over
equity, bands, thresholds and freshness. What is missing is the reading, not the maths, and
`_broker_snapshot` is the single function that changes when a connector lands.

`dashboard()` deliberately fails rather than returning zeros, last-known values, or a
partially-filled dict with `success: true`. Every one of those alternatives produces a dashboard
that looks like it is working.

---

## The open range-start question

Unchanged from [the bot's README](../src/LondonBreakout/README.md), and now visible in the backend
too: **where does the range start?** London midnight builds it over the Asian session; the
Pepperstone daily boundary (17:00 New York) starts an hour or two earlier and matches the
platform's daily candle. The two give materially different results and only a multi-year backtest
can choose between them.

`strategy_spec.validate_spec()` currently **refuses** a spec whose `range_start` is later in the day
than its `signal`, with an error naming this question. That is not a decision about the answer — it
is the overnight-wrap limitation stated where it bites. 17:00 New York is 22:00/23:00 London *the
previous day*, so answering the question that way needs a range that wraps past midnight, which
neither the cBot nor this spec format supports. Refusing loudly beats accepting a spec the runtime
would silently mis-measure.

Two other things this schema does not yet settle, listed so they are not mistaken for decisions:

- **Spec versioning across `kind`s.** Only `session_breakout` exists. A second strategy shape means
  either a second validator or a discriminated spec — worth deciding before the second strategy,
  not during it.
- **Where margin thresholds come from.** `margin_thresholds()` serves conventional retail defaults
  labelled `source: "defaults"`. Real values are broker- and account-specific and arrive with the
  connector.

---

## Two follow-ups that cannot be done from this repository

**1. The composer manifest has to be PR'd into the protocol repo.**

[`composer/forex.json`](../composer/forex.json) does nothing where it sits. It has to be:

- PR'd into `RokctAI/The-Rokct-Protocol` at `core/utils/flutter/composer/forex.json`, **and**
- copied to the app repo root as `composer.json`.

**CI silently skips composition when that root file is missing** — no error, no warning; the app
simply builds with no SDKs in it. That failure mode is the reason this is called out here rather
than left as an implicit step.

**2. Promote `CardDeck<T>` / `DealtCard` / `PageDots` from `agent/lms` into `base_sdk`.**

They live at `agent/lms/dart/lib/src/common/presentation/widgets/{card_deck,dealt_card,page_dots}.dart`.
They are generic — a deck, a dealt card, a dots indicator, with no LMS logic in them — and forex
wants the same card engine for the strategy catalog and the plans sheet.

ADR-005 blocks the shortcut: `forex_sdk` may not import `lms_sdk`, so it cannot simply reuse them
where they are. Copying them would be two divergent decks within a year. The right move is
promoting them into `base_sdk`'s shared presentation components and having `lms_sdk` re-export from
there during the transition — a change in `RokctAI/core` and `RokctAI/agent`, not here. Until that
lands, the strategy list is a plain `ListView`.

---

## Layout

```
forex_sdk/
├── frappe/
│   ├── manifest.json                 # rforex: app_type personas (tenant populated, control empty)
│   └── src/tenant/                   # tenant-persona code; stripped from control-marked shells
│       ├── doctype/<six doctypes>/   # __init__.py, <name>.json, <name>.py (composer relocates to module root)
│       └── rforex/
│           ├── risk_presets.py       # pure
│           ├── strategy_spec.py      # pure
│           ├── margin.py             # pure
│           ├── entitlements.py       # pure
│           ├── api/                  # strategy, account, credential, entitlement, risk
│           └── tests/                # 161 tests, plain unittest
└── dart/
    ├── pubspec.yaml, analysis_options.yaml, install.py, manifest.json
    ├── lib/forex_sdk.dart            # barrel
    ├── lib/src/common/
    │   ├── domain/{models,interface}/
    │   ├── infrastructure/repositories/
    │   ├── presentation/pages/
    │   ├── di/  constants/
    └── templates/routes/forex_route_pages.dart   # host glue + adapters
```

There is no `application/` layer yet. The house layout has one and forex will need it — but the two
screens here hold their own state, and an empty notifier layer with nothing to coordinate is
scaffolding for its own sake. It arrives with the first screen that needs cross-widget state, which
will be the account dashboard.

---

## Verification status, stated exactly

- **Python: run.** `python3 -m unittest discover -s tests -t .` → **161 tests, 0 failures.**
- **Dart: not run.** No Flutter or Dart toolchain exists in the environment this was written in
  (`which flutter dart` finds nothing). The Dart has been reviewed by hand and bracket-checked, but
  **it has not been analysed, compiled or tested**, and it should be assumed to have the kind of
  mistakes that only `flutter analyze` catches. First job for anyone with a toolchain:
  `cd forex_sdk/dart && flutter pub get && flutter analyze`.
- **.NET: untouched.** This SDK is additive; `LondonBreakout.sln`, `src/LondonBreakout*` and
  `tests/` are unchanged, and CI builds and tests the solution by name.
