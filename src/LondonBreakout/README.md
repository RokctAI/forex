# London Breakout cBot

A rule-based London breakout straddle for cTrader Algo. It measures the pre-session range,
then places a buy stop above it and a sell stop below it, both protected by server-side stops
and targets, with position size derived from a fixed-fractional risk budget.

The bot runs on whatever symbol and chart it is attached to. Nothing is hardcoded to a pair.

---

## The strategy as implemented

1. **Build the range.** From `RangeStartHour:RangeStartMinute` (default 00:00 London) up to
   `SignalHour:SignalMinute` (default 09:00 London), record the highest high and lowest low.
   The high is resistance, the low is support.
2. **Wait for the signal time.** Nothing is placed before 09:00 London. The bar that *opens* at
   09:00 is excluded from the range — it belongs to the period being traded, and including it
   would leak future information into the entry levels.
3. **Place both sides.** A buy stop at `rangeHigh + EntryBufferPips` and a sell stop at
   `rangeLow - EntryBufferPips`. Both entries sit strictly outside the range: the bot never
   enters inside the lines.
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
| `Trading days` | `Mon,Tue,Wed,Thu,Fri` | **Open question** — see below. |
| `Range timeframe` | `Minute5` | Bar size used to measure the range. |
| `Minimum range bars` | `12` | Reject the session below this many bars (holidays, feed gaps, mid-session starts). |
| `Placement grace (minutes)` | `30` | How late after the signal orders may still be placed. |

### Strategy

| Parameter | Default | Notes |
|---|---|---|
| `Entry buffer (pips)` | `1.0` | How far outside each range edge the stop order sits. |
| `Stop mode` | `OppositeRangeSide` | **Open question.** Or `FixedPips` / `AtrMultiple`. |
| `Fixed stop (pips)` | `20.0` | Used only by `FixedPips`. |
| `ATR periods` | `14` | Used only by `AtrMultiple`. |
| `ATR multiplier` | `1.5` | Used only by `AtrMultiple`. |
| `Target (R multiple)` | `1.0` | **Open question.** 1.0 = target as far away as the stop. |
| `Min range (pips)` | `5.0` | Skip narrow ranges — a tight stop implies a huge position. |
| `Max range (pips)` | `0.0` | `0` disables. |
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

## Open questions

These were not specified. Each has a documented default and is a parameter — none of them is
guessed silently in code.

- [ ] **Tuesday only, or every weekday?** The original description said "the highest price of
      Tuesday until 9am". Defaulted to Mon–Fri via `Trading days`; set it to `Tue` for
      Tuesday-only.
- [ ] **When does the range start?** Broker day open, London midnight, or the Asian session?
      Defaulted to 00:00 in the session timezone.
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

## Testing path

**1. Backtest in tick mode, not M1-bar mode.**

In the cTrader backtester choose **"Tick data (from server)"**. The faster M1-bar modes model
each minute as a synthetic OHLC path with a *fixed* spread, which systematically flatters
breakout entries: stop orders sitting a pip outside a level get filled at the level in the
model, where live they pay a widening spread. 09:00 London is a session open — precisely when
spreads widen. Backtest results from bar mode will be optimistic and should not be trusted for
this strategy.

**2. Then a demo account for at least a few weeks**, spanning a BST boundary if possible, to
confirm the session times track correctly. Watch the log line printed at startup: it reports
the resolved timezone and its *current* UTC offset.

**3. Only then consider live, at the smallest size the broker allows.**

### Running the unit tests

```bash
dotnet test
```

80 tests cover the sizing arithmetic, the range/session logic, DST transitions and the risk
guards. They do not require the cTrader assembly or a Windows host.

### Building

```bash
dotnet build LondonBreakout.sln
```

Produces `LondonBreakout.algo`, which cTrader loads. The build also copies it into the local
cTrader sources folder if one exists.

---

## Known limitations

- **Not yet backtested or run on a demo account.** The code compiles and the pure logic is unit
  tested, but no market data has been through it. Treat the parameter defaults as starting
  points, not as tuned values.
- Overnight ranges that wrap past midnight are rejected at construction; the range start must be
  earlier in the day than the signal time.
- The bot manages only its own orders, matched by `Order label`. Positions opened by hand or by
  another bot are invisible to it, except through account-level equity and margin.
- `MaxConcurrentPositions` counts only this bot's positions on this symbol.
