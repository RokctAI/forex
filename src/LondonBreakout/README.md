# London Breakout cBot

A rule-based London breakout straddle for cTrader Algo. It measures the pre-session range,
then places a buy stop above it and a sell stop below it, both protected by server-side stops
and targets, with position size derived from a fixed-fractional risk budget.

**Nothing here has ever seen market data.** It has not been backtested and has not been run on
a demo or live account. Every default below is a documented starting point, not a tuned value.

## The specification

| | |
|---|---|
| **Days** | **Tuesday only.** Monday is an explicit stay-away day, and so is every other weekday. |
| **Primary symbol** | **GBPJPY.** |
| **Secondary symbol** | GBPUSD — also works, but it is not the same instrument in risk terms. See [Two symbols, one parameter set](#two-symbols-one-parameter-set). |
| **Broker** | Pepperstone. |
| **Trader location** | South Africa — so the account is likely ZAR or USD, while GBPJPY settles pips in JPY. This is why pip value must come from the platform. |
| **Range start** | **Still unanswered.** See [Open questions](#open-questions). Defaults to 00:00 in the session timezone. |

> ### Read this before backtesting
>
> **Trading one day a week caps this strategy at about 52 opportunities a year, and not every
> Tuesday will produce a fill** — range filters, the risk guards and simply not breaking out all
> remove sessions. A realistic fill rate puts a single year somewhere in the 30s or 40s of
> trades, before any filter is counted.
>
> **A backtest needs at least five years of tick data before the result means anything.** One
> year cannot clear the usual ≥30-trade bar with any margin at all: even if it technically
> reaches 30 fills, the confidence interval around a win rate from that sample is wide enough to
> contain both "profitable" and "loses money steadily". A single good or bad year of GBPJPY
> would dominate the answer.
>
> This is the most important caveat on the whole project. It is not a reason to abandon the
> strategy — it is a reason to refuse to draw conclusions from a short test, and to expect the
> honest verdict after five years of data to still be "promising" rather than "proven".

The bot runs on whatever symbol and chart it is attached to; nothing is hardcoded to a pair.
Attach one instance per symbol, each with its own `Order label`.

---

## The strategy as implemented

0. **Only on a trading day.** Tuesday, by default and by specification. Every other day the bot
   reads the clock and does nothing.
1. **Build the range.** From `RangeStartHour:RangeStartMinute` (default 00:00 London) up to
   `SignalHour:SignalMinute` (default 09:00 London), record the highest high and lowest low.
   The high is resistance, the low is support.
2. **Wait for the signal time.** Nothing is placed before 09:00 London. The bar that *opens* at
   09:00 is excluded from the range — it belongs to the period being traded, and including it
   would leak future information into the entry levels.
3. **Place both sides.** A buy stop at `rangeHigh + buffer` and a sell stop at
   `rangeLow - buffer`, where the buffer defaults to a multiple of the symbol's own ATR rather
   than a fixed pip count. Both entries sit strictly outside the range: the bot never enters
   inside the lines.
4. **Protect at submission.** Each order carries a stop loss, a take profit and an expiry as
   order attributes, so they live on the broker's servers rather than in this process.
5. **Cancel the loser.** When one leg fills, the other is cancelled (configurable).

Both legs are given the **same stop distance** by construction. That is what makes a single
`RiskPercent` figure meaningful: the loss is identical whichever way price breaks.

---

## Parameters

### Session

| Parameter | Default | Notes |
|---|---|---|
| `Session timezone` | `Europe/London` | IANA or Windows id. Accepts `GMT Standard Time` too. |
| `Range start hour` | `0` | **Open question** — see below. |
| `Range start minute` | `0` | |
| `Signal hour` | `9` | Range ends and orders go in at this time. |
| `Signal minute` | `0` | |
| `Trading days` | `Tue` | Tuesday only, as specified. Still a parameter, but widening it is a research change. |
| `Range timeframe` | `Minute5` | Bar size used to measure the range. |
| `Minimum range bars` | `12` | Reject the session below this many bars (holidays, feed gaps, mid-session starts). |
| `Placement grace (minutes)` | `30` | How late after the signal orders may still be placed. |

### Strategy

| Parameter | Default | Notes |
|---|---|---|
| `Reference ATR timeframe` | `Daily` | The ATR every volatility-relative setting is a multiple of. |
| `ATR periods` | `14` | Periods for that ATR. |
| `Entry buffer mode` | `AtrMultiple` | Or `Pips`. |
| `Entry buffer (pips)` | `1.0` | Used only by `Pips`. |
| `Entry buffer (x ATR)` | `0.05` | Used only by `AtrMultiple`. ≈6 pips on GBPJPY, ≈3.5 on GBPUSD. |
| `Stop mode` | `OppositeRangeSide` | **Open question.** Or `FixedPips` / `AtrMultiple`. |
| `Fixed stop (pips)` | `20.0` | Used only by `FixedPips`. Symbol-specific — see below. |
| `ATR multiplier` | `0.5` | Used only by stop mode `AtrMultiple`. A multiple of the **daily** ATR. |
| `Target (R multiple)` | `1.0` | **Open question.** 1.0 = target as far away as the stop. |
| `Range filter mode` | `AtrMultiple` | Or `Pips`. Applies to both the min and max filters. |
| `Min range (pips)` | `5.0` | Used only by `Pips`. |
| `Min range (x ATR)` | `0.25` | Used only by `AtrMultiple`. Skip unusually quiet sessions. |
| `Max range (pips)` | `0.0` | Used only by `Pips`. `0` disables. |
| `Max range (x ATR)` | `0.0` | Used only by `AtrMultiple`. `0` disables. |
| `Cancel sibling on fill (OCO)` | `true` | **Open question.** |
| `Order expiry (hours)` | `8.0` | Server-side expiry, measured from the signal time. |
| `Order label` | `LondonBreakout` | Give each instance its own label if running several. |

### Risk

| Parameter | Default | Notes |
|---|---|---|
| `Trading enabled (kill switch)` | `true` | Master switch, consulted before every entry. |
| `Risk per trade (%)` | `0.5` | Percentage of equity lost if the stop is hit. |
| `Max daily loss (%)` | `2.0` | No new positions for the rest of the day once breached. `0` disables. |
| `Max drawdown (%)` | `10.0` | From the equity peak. Flattens and halts; manual restart required. `0` disables. |
| `Max concurrent positions` | `1` | |
| `Max margin utilisation (%)` | `20.0` | Refuse entries above this share of equity in margin. `0` disables. |
| `Over-risk tolerance (%)` | `10.0` | Refuse the trade if the broker's minimum lot over-risks by more than this. |
| `Poll interval (seconds)` | `5` | How often the clock and guards are checked. |

---

## Two symbols, one parameter set

GBPJPY and GBPUSD are not interchangeable, and the difference bites in two separate ways.

**1. Quote precision — a units problem, and it is solved.**

GBPJPY is quoted to 3 decimals, so one pip is `0.01`. GBPUSD is quoted to 5, so one pip is
`0.0001`. Every conversion between a price distance and a pip count reads `Symbol.PipSize`
rather than assuming a constant, so a 50-pip stop is correctly `0.50` on GBPJPY and `0.0050` on
GBPUSD. Hardcoding `0.0001` would size every GBPJPY position **100× wrong** — and the resulting
number still looks like a plausible volume, which is what makes the mistake dangerous rather
than obvious. `SymbolParityTests` pins this on both precisions.

**2. Typical range — not a units problem, and not fixable by arithmetic.**

GBPJPY's typical daily range is roughly **double** GBPUSD's in pip terms. So "20 pips" is a much
tighter distance on GBPJPY than the same number is on GBPUSD, measured by the only thing that
matters: how likely price is to travel it. A buffer, range floor or stop tuned on one symbol is
therefore mis-scaled on the other *even when the pip maths is perfect*.

The fix is to express those distances as multiples of the symbol's own ATR, which is why
`AtrMultiple` is the default for the entry buffer and the range filters. The same multiplier
then means the same thing on both symbols. Fixed pips remain available for anyone who wants an
exact, symbol-specific number — but a fixed-pip value is only ever correct for one symbol.

The reference ATR is a **daily** ATR on purpose. The point of these settings is to scale with how
far the symbol travels in a day, which is exactly what differs between the two pairs; an
intraday ATR does not capture it. It is read from the last **closed** daily bar, so the session
being traded cannot feed back into the levels used to trade it.

If the ATR is unavailable (insufficient history), sessions using ATR-relative settings are
**skipped**, not silently run on a pip fallback. A silent fallback is precisely how a value
tuned for one symbol ends up applied to the other.

**Pip value and the account currency.**

A pip on GBPJPY is earned in **JPY**, because JPY is the quote currency. The account is ZAR or
USD. So the account-currency value of a GBPJPY pip moves with GBPJPY *and* with JPY/ZAR (or
JPY/USD) — it drifts even on a day GBPJPY does not move.

Inside a cBot this is already handled: `Symbol.PipValue` is quoted in the deposit currency and
cTrader keeps the conversion leg current. The sizer takes that number and multiplies; it never
reconstructs it. **This is the single thing a port to an external market-data API would get
wrong** — such an API hands back a raw quote and nothing else, and a naive port multiplies by
`0.0001` or by a contract size and produces sizes wrong by whatever JPY/ZAR happens to be. Any
such port must source a live conversion rate and apply it explicitly. See the comment on
`SymbolConstraints.PipValuePerUnit`.

---

## Open questions

These were not specified. Each has a documented default and is a parameter — none of them is
guessed silently in code.

- [ ] **When does the range start?** *Still open, and it matters more than the others.* The two
      candidate answers give **materially different ranges and therefore different trades**:
      - **London midnight** (current default) — the range is the ~9 hours of Asian-session
        trading before London opens.
      - **The broker's daily boundary** — Pepperstone's trading day rolls at **17:00 New York**,
        which is 22:00 or 23:00 London depending on the date. That range starts an hour or two
        earlier and is anchored to the broker's daily candle, so it matches what a "daily bar"
        shows on the platform.

      They are not small variations of each other: they build the range over different windows,
      so the high, the low, the entry levels and the stop distance all differ. Backtest both
      before picking. Change with `Range start hour` / `Range start minute` (and note that a
      22:00 start would need the overnight-wrap limitation below lifted first).
- [ ] **Which 09:00 candle?** Implemented as: the range ends *at* 09:00, and orders are placed
      as soon as the bar ending at 09:00 has closed. The alternative reading — wait for the
      09:00→10:00 bar to close — leaves an untraded hour where price is neither in the range nor
      acted on. Change `Signal hour` to `10` for that reading.
- [ ] **Stop rule?** Defaulted to the opposite side of the range. `FixedPips` and `AtrMultiple`
      are implemented too.
- [ ] **Target rule?** Defaulted to 1.0R.
- [ ] **Should the sibling order stay live after the first fills?** Defaulted to cancelling it.

---

## Design notes

### Timezone handling

Broker server time is not London time, and London observes BST. Three clocks are in play and
conflating any two breaks the bot for part of the year:

- **Broker/server time** — commonly EET/UTC+2/UTC+3, with its own DST calendar.
- **UTC** — stable, the only safe interchange format.
- **London civil time** — UTC+0 in winter, UTC+1 in summer, on UK statutory dates that do not
  coincide with US or EU switchovers.

A fixed offset is wrong for roughly half the year. So the bot declares itself
`[Robot(TimeZone = TimeZones.UTC)]` — which makes `Server.Time` and every `Bars.OpenTimes`
value arrive in UTC — and resolves London wall-clock times through `TimeZoneInfo`. The DST
edge cases are handled explicitly: a session time falling in the spring-forward gap rolls
forward, and an ambiguous fall-back time deterministically takes the first occurrence.

`SessionClock.ResolveTimeZone` accepts both IANA and Windows ids, because cTrader runs on
Windows (Windows ids) while CI runs on Linux (IANA ids), and one parameter value has to work
in both places.

### Native OCO — verified finding

**The cTrader Algo API has no native one-cancels-other facility for pending orders.**

This was verified directly rather than inferred: the shipped `cAlgo.API.dll` from
`cTrader.Automate` 1.0.19 was reflected over and its entire public surface searched. The
`PendingOrder` interface exposes no linked-order, OCO-group or sibling property, and no
`PlaceStopOrder` / `PlaceLimitOrder` overload accepts one. (The OCO/OSO products in the cTrader
Store are third-party tools that implement the behaviour themselves, not an API feature.)

`help.ctrader.com` is blocked by this environment's network proxy, so the official documentation
could not be read — but reflecting over the actual assembly is stronger evidence than the docs
would have been.

So the sibling cancel is done in code, in `Positions.Opened`. **This is exactly why the
server-side expiry is not optional.** The cancel handler only runs if the bot is alive; if one
leg fills and the process dies before the cancel, the surviving order would otherwise sit there
and could open an unwanted opposite position days later. The expiry makes that orphan clean
itself up broker-side.

### Everything safety-critical is a server-side attribute

Stop loss, take profit and expiry are all passed to `PlaceStopOrder` at submission, using
`ProtectionType.Absolute` so the levels are exact prices rather than rounded pip distances.
They then survive the bot being stopped, the platform being closed, or the machine losing
power. A stop that only exists inside a running bot is not a stop.

### No trading on ticks

The bot polls on a timer (default 5s) and never acts on raw ticks. cTrader rate-limits algo
trading operations, and breaching the limit blocks **manual** trading on the account too. At
most two orders are placed per session.

### Structure

`LondonBreakout.Core` holds all the logic that can be got wrong — DST resolution, range
computation, position sizing, risk gating — and has **zero dependency on cAlgo.API**, so it is
unit-testable on any machine. `LondonBreakoutBot` is a thin shell: `OnStart`, `OnTimer`,
`Positions.Opened`, `OnStop`.

The cBot project compiles the Core sources in by `<Compile Include>` rather than using a
`ProjectReference`. The cTrader.Automate targets bundle build output into a single `.algo`, and
a second assembly is not guaranteed to be carried into that bundle — which would give a bot that
builds cleanly and then fails at load time. Linking the sources puts everything in one assembly.

---

## How to actually run the backtest

Start from the sample-size warning at the top of this file: **at least five years of tick data,
on both symbols.** Anything shorter does not produce a result worth interpreting, and the single
most common way to waste this work is to run one year, see a number, and believe it.

**1. Use cTrader Desktop, not the web terminal.** Only the desktop application has the full
backtester with tick data and the optimisation tools.

**2. Choose tick data mode — "Tick data (from server)". Not the M1-bar modes.**

This is not a speed-versus-accuracy preference; for this strategy the bar modes are actively
misleading. They model each minute as a synthetic OHLC path with a **fixed spread**, which
systematically flatters breakout entries: a stop order sitting a few pips outside a level gets
filled at the level in the model, where live it pays a spread that is widening at that exact
moment. 09:00 London is a session open — precisely when spreads widen, and precisely when this
bot places its orders. Bar-mode results for a breakout strategy will be optimistic. GBPJPY makes
this worse, as it is the wider-spread pair of the two.

Downloading five years of tick data for two symbols takes a while. Do it once and let it cache.

**3. Run both symbols separately.** GBPJPY is the primary and GBPUSD the secondary; they are
different instruments in risk terms, so they get separate results. Do not average them, and do
not treat GBPUSD confirming GBPJPY as independent evidence — the two are correlated through GBP,
so a good GBP year lifts both.

**4. Split in-sample and out-of-sample before looking at anything.** With five years, hold back
the most recent one to two years entirely. Tune on the in-sample period only, then run the
held-back period **once**. If the out-of-sample result disappoints, that is the answer; going
back to re-tune and re-running it converts the held-back data into in-sample data and destroys
the only honest check available. Given ~52 chances a year, there is very little room to fit
parameters before fitting noise — prefer the fewest changes that work.

**5. Pad the slippage manually.** Even in tick mode the backtester does not fully model what
happens to a stop order at a session open. Add commission at the broker's real rate, then re-run
the promising configurations with an extra allowance — a pip or two on GBPUSD and more on GBPJPY
is a reasonable starting assumption — and see whether the edge survives. If it only works at
zero slippage, it does not work.

**6. Also test both answers to the range-start question**, since they are different strategies in
practice. See [Open questions](#open-questions).

**7. Then a demo account for at least a few weeks**, spanning a BST boundary if possible, to
confirm the session times track correctly. Watch the log lines printed at startup: they report
the resolved timezone with its *current* UTC offset, and the symbol's digits, pip size and pip
value. On GBPJPY that line should read 3 digits and a `0.01` pip; on GBPUSD, 5 and `0.0001`. If
it does not, stop — nothing downstream can be right.

Bear in mind that a few weeks of Tuesdays is **a handful of trades**. Demo running confirms the
plumbing — session times, order placement, OCO, sizing — and tells you nothing whatsoever about
whether the strategy makes money.

**8. Only then consider live, at the smallest size the broker allows.**

### Running the unit tests

```bash
dotnet test
```

97 tests cover the sizing arithmetic, the range/session logic, DST transitions, the risk guards,
and per-symbol behaviour across a 3-digit JPY-quoted symbol and a 5-digit one. They do not
require the cTrader assembly or a Windows host.

### Building

```bash
dotnet build LondonBreakout.sln
```

Produces `LondonBreakout.algo`, which cTrader loads. The build also copies it into the local
cTrader sources folder if one exists.

---

## Known limitations

- **Not yet backtested or run on a demo account.** The code compiles and the pure logic is unit
  tested, but **no market data has ever been through it.** Treat the parameter defaults as
  starting points, not as tuned values.
- **One day a week is a small sample.** ~52 opportunities a year before filters. See the warning
  at the top: five years of data minimum, and expect "promising" rather than "proven" even then.
- **The broker-boundary range start cannot currently be configured.** Overnight ranges that wrap
  past midnight are rejected at construction — the range start must be earlier in the day than
  the signal time. A 17:00 New York start is 22:00/23:00 London, i.e. the previous day, so
  answering the range-start open question that way needs the wrap limitation lifted first.
- The volatility-relative defaults (`0.05 x ATR` buffer, `0.25 x ATR` range floor) are reasoned
  starting points, not measured ones. They are the first thing to vary in the in-sample period.
- The bot manages only its own orders, matched by `Order label`. Positions opened by hand or by
  another bot are invisible to it, except through account-level equity and margin.
- `MaxConcurrentPositions` counts only this bot's positions on this symbol.
