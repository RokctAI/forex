# forex

Autonomous, rule-based forex trading bots with automated money management, built as **cBots for
cTrader Algo** (C# / net6.0, `cTrader.Automate`).

The direction is a set of strategies that a non-expert can run by picking a preset — no tuning,
no discretionary decisions, and risk controls that cannot be bypassed by the strategy layer.

## Contents

| Path | What it is |
|---|---|
| [`src/LondonBreakout/`](src/LondonBreakout/README.md) | London breakout straddle cBot. Range to 09:00 London, buy stop above / sell stop below. **Tuesdays only; GBPJPY primary, GBPUSD secondary.** |
| `src/LondonBreakout.Core/` | Pure strategy logic — sessions/DST, range computation, position sizing, risk guards. No cTrader dependency. |
| `tests/LondonBreakout.Core.Tests/` | Unit tests for the above. |
| [`forex_sdk/`](forex_sdk/README.md) | The app and backend around the bots — strategy catalog, risk presets, broker credentials, entitlement. A Rokct SDK pair (`dart/` + `frappe/`). **Skeleton.** |
| [`composer/forex.json`](composer/forex.json) | App composer manifest. Has to be PR'd into the protocol repo and copied to the app root — see the SDK README. |

## Repository conventions

- **cBots, not Open API apps.** Strategies run inside cTrader as `.algo` packages rather than as
  external processes talking to the Open API.
- **Pure logic is separated from the platform.** Anything that can be got wrong — timezone and
  DST resolution, sizing arithmetic, risk gating — lives in a `*.Core` project with no
  `cAlgo.API` dependency, so it is unit-testable without the trading assembly or a Windows host.
  The `Robot` subclass stays a thin shell.
- **Risk lives in its own layer.** Position sizing and the account-level guards are separate
  from the strategy, and the strategy has to ask permission before every entry.
- **Safety-critical instructions are server-side.** Stops, targets and expiries are attached at
  order submission so they survive the bot dying.

## Building and testing

Requires the .NET SDK (8.x is fine; the cBot targets net6.0).

```bash
dotnet build LondonBreakout.sln
dotnet test
```

The SDK's backend rules are pure Python with no Frappe, no site and no database:

```bash
cd forex_sdk/frappe/src/tenant/rforex && python3 -m unittest discover -s tests -t .
```

The Dart package needs a Flutter toolchain, which CI does not currently install:

```bash
cd forex_sdk/dart && flutter pub get && flutter analyze
```

The build produces `LondonBreakout.algo` and, where a local cTrader installation exists, copies
it into the cTrader sources folder.

Both commands run in CI on every push and pull request — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Status

Early. The London breakout bot compiles and its pure logic is unit tested (97 tests), but
**no market data has ever been through it** — nothing here has been backtested or run against a
live or demo account.

`forex_sdk/` is a skeleton: the schema, the rules and the boundaries are settled and unit tested
(161 tests), but there is no broker connector, so the account dashboard has no numbers to show and
says so rather than showing placeholders. Its README lists exactly what is stubbed.

The strategy is now specified as **Tuesday only**, on **GBPJPY** primarily and GBPUSD
secondarily. That carries a consequence worth stating on the front page: one trading day a week
is roughly **52 opportunities a year**, and not every Tuesday produces a fill. **A backtest needs
at least five years of tick data before its result means anything** — a single year cannot clear
the usual ≥30-trade bar with any margin.

See the [bot's README](src/LondonBreakout/README.md) for how to run that backtest properly, the
per-symbol pip handling that GBPJPY demands, and the remaining open questions.
