# forex

Autonomous, rule-based forex trading bots with automated money management, built as **cBots for
cTrader Algo** (C# / net6.0, `cTrader.Automate`).

The direction is a set of strategies that a non-expert can run by picking a preset — no tuning,
no discretionary decisions, and risk controls that cannot be bypassed by the strategy layer.

## Contents

| Path | What it is |
|---|---|
| [`src/LondonBreakout/`](src/LondonBreakout/README.md) | London breakout straddle cBot. Range to 09:00 London, buy stop above / sell stop below. |
| `src/LondonBreakout.Core/` | Pure strategy logic — sessions/DST, range computation, position sizing, risk guards. No cTrader dependency. |
| `tests/LondonBreakout.Core.Tests/` | Unit tests for the above. |

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

The build produces `LondonBreakout.algo` and, where a local cTrader installation exists, copies
it into the cTrader sources folder.

## Status

Early. The London breakout bot compiles and its pure logic is unit tested, but **nothing here
has been backtested or run against a live or demo account yet.** See the bot's own README for
the recommended testing path and its list of open questions.
