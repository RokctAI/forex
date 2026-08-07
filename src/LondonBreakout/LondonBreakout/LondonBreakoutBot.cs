using System;
using System.Collections.Generic;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;
using LondonBreakout.Core.Planning;
using LondonBreakout.Core.Ranges;
using LondonBreakout.Core.Risk;
using LondonBreakout.Core.Sessions;

namespace LondonBreakout
{
    /// <summary>
    /// London breakout straddle.
    ///
    /// Builds a range from the session start (default 00:00 London) up to the signal time
    /// (default 09:00 London), then places a buy stop just above the range high and a sell stop
    /// just below the range low. Both carry a server-side stop loss, take profit and expiry.
    /// When one fills, the other is cancelled.
    ///
    /// This class is deliberately a thin shell. All the logic that can be got wrong -- timezone
    /// and DST resolution, range computation, position sizing, risk gating -- lives in
    /// LondonBreakout.Core, which has no cTrader dependency and is covered by unit tests.
    ///
    /// The bot declares itself as UTC so that Server.Time and every Bars.OpenTimes value arrive
    /// in UTC. London wall-clock times are then derived through TimeZoneInfo, which tracks BST
    /// automatically. See SessionClock for the full rationale.
    /// </summary>
    [Robot(
        AccessRights = AccessRights.None,
        TimeZone = TimeZones.UTC,
        AddIndicators = true)]
    public class LondonBreakoutBot : Robot
    {
        // ---------------------------------------------------------------- Session parameters

        [Parameter("Session timezone", Group = "Session", DefaultValue = "Europe/London",
            Description = "IANA ('Europe/London') or Windows ('GMT Standard Time') id. Session times " +
                          "are wall-clock times in this zone and follow its DST rules automatically.")]
        public string SessionTimeZoneId { get; set; }

        [Parameter("Range start hour", Group = "Session", DefaultValue = 0, MinValue = 0, MaxValue = 23,
            Description = "OPEN QUESTION: broker day open, London midnight or Asian session? Defaults to " +
                          "00:00 in the session timezone.")]
        public int RangeStartHour { get; set; }

        [Parameter("Range start minute", Group = "Session", DefaultValue = 0, MinValue = 0, MaxValue = 59)]
        public int RangeStartMinute { get; set; }

        [Parameter("Signal hour", Group = "Session", DefaultValue = 9, MinValue = 0, MaxValue = 23,
            Description = "The range ends and orders are placed at this time. Bars opening at or after " +
                          "it are excluded from the range.")]
        public int SignalHour { get; set; }

        [Parameter("Signal minute", Group = "Session", DefaultValue = 0, MinValue = 0, MaxValue = 59)]
        public int SignalMinute { get; set; }

        [Parameter("Trading days", Group = "Session", DefaultValue = "Mon,Tue,Wed,Thu,Fri",
            Description = "OPEN QUESTION: every weekday or Tuesday only? Comma-separated day names.")]
        public string TradingDays { get; set; }

        [Parameter("Range timeframe", Group = "Session", DefaultValue = "Minute5",
            Description = "Bar size used to measure the range high/low. Finer is more accurate; m5 is a " +
                          "reasonable balance against history size.")]
        public TimeFrame RangeTimeFrame { get; set; }

        [Parameter("Minimum range bars", Group = "Session", DefaultValue = 12, MinValue = 1,
            Description = "Reject the session if fewer bars than this fall inside the range window. " +
                          "Guards against holidays, data gaps and mid-session starts.")]
        public int MinimumRangeBars { get; set; }

        [Parameter("Placement grace (minutes)", Group = "Session", DefaultValue = 30, MinValue = 1,
            Description = "How long after the signal time orders may still be placed. Stops a bot " +
                          "restarted at lunchtime from entering a morning breakout that already played out.")]
        public int PlacementGraceMinutes { get; set; }

        // ---------------------------------------------------------------- Strategy parameters

        [Parameter("Entry buffer (pips)", Group = "Strategy", DefaultValue = 1.0, MinValue = 0.0, Step = 0.1,
            Description = "How far beyond the range edge each stop order sits.")]
        public double EntryBufferPips { get; set; }

        [Parameter("Stop mode", Group = "Strategy", DefaultValue = StopMode.OppositeRangeSide,
            Description = "OPEN QUESTION: no stop rule was specified. Defaults to the opposite side of " +
                          "the range.")]
        public StopMode StopLossMode { get; set; }

        [Parameter("Fixed stop (pips)", Group = "Strategy", DefaultValue = 20.0, MinValue = 0.1,
            Description = "Only used when Stop mode is FixedPips.")]
        public double FixedStopPips { get; set; }

        [Parameter("ATR periods", Group = "Strategy", DefaultValue = 14, MinValue = 1)]
        public int AtrPeriods { get; set; }

        [Parameter("ATR multiplier", Group = "Strategy", DefaultValue = 1.5, MinValue = 0.1, Step = 0.1,
            Description = "Only used when Stop mode is AtrMultiple.")]
        public double AtrMultiplier { get; set; }

        [Parameter("Target (R multiple)", Group = "Strategy", DefaultValue = 1.0, MinValue = 0.1, Step = 0.1,
            Description = "OPEN QUESTION: no target rule was specified. 1.0 means the target sits the same " +
                          "distance away as the stop.")]
        public double TargetRMultiple { get; set; }

        [Parameter("Min range (pips)", Group = "Strategy", DefaultValue = 5.0, MinValue = 0.0, Step = 0.5,
            Description = "Skip the session if the range is narrower than this. A tight stop implies a " +
                          "very large position, so this is a sizing safeguard.")]
        public double MinRangePips { get; set; }

        [Parameter("Max range (pips)", Group = "Strategy", DefaultValue = 0.0, MinValue = 0.0, Step = 1.0,
            Description = "Skip the session if the range is wider than this. 0 disables the check.")]
        public double MaxRangePips { get; set; }

        [Parameter("Cancel sibling on fill (OCO)", Group = "Strategy", DefaultValue = true,
            Description = "OPEN QUESTION: should the other side stay live after one fills? Default is to " +
                          "cancel it. The cTrader Algo API has no native OCO, so this is done in code.")]
        public bool CancelSiblingOnFill { get; set; }

        [Parameter("Order expiry (hours)", Group = "Strategy", DefaultValue = 8.0, MinValue = 0.5, Step = 0.5,
            Description = "Server-side expiry on each pending order, measured from the signal time. This " +
                          "is what cleans up an orphaned leg if the bot dies mid-session.")]
        public double OrderExpiryHours { get; set; }

        [Parameter("Order label", Group = "Strategy", DefaultValue = "LondonBreakout",
            Description = "Identifies this bot's orders and positions. Give each instance its own label " +
                          "if you run several on one account.")]
        public string OrderLabel { get; set; }

        // -------------------------------------------------------------------- Risk parameters

        [Parameter("Trading enabled (kill switch)", Group = "Risk", DefaultValue = true,
            Description = "Master switch. When off, nothing is placed regardless of any other setting.")]
        public bool TradingEnabled { get; set; }

        [Parameter("Risk per trade (%)", Group = "Risk", DefaultValue = 0.5, MinValue = 0.01, MaxValue = 100.0, Step = 0.1,
            Description = "Percentage of equity risked if the stop is hit.")]
        public double RiskPercent { get; set; }

        [Parameter("Max daily loss (%)", Group = "Risk", DefaultValue = 2.0, MinValue = 0.0, Step = 0.1,
            Description = "No new positions for the rest of the day once the day's loss reaches this. " +
                          "0 disables.")]
        public double MaxDailyLossPercent { get; set; }

        [Parameter("Max drawdown (%)", Group = "Risk", DefaultValue = 10.0, MinValue = 0.0, Step = 0.5,
            Description = "Measured from the equity peak. Breaching it flattens everything and halts the " +
                          "bot until a human restarts it. 0 disables.")]
        public double MaxDrawdownPercent { get; set; }

        [Parameter("Max concurrent positions", Group = "Risk", DefaultValue = 1, MinValue = 1)]
        public int MaxConcurrentPositions { get; set; }

        [Parameter("Max margin utilisation (%)", Group = "Risk", DefaultValue = 20.0, MinValue = 0.0, Step = 1.0,
            Description = "Refuse new entries when used margin exceeds this share of equity. 0 disables.")]
        public double MaxMarginUtilisationPercent { get; set; }

        [Parameter("Over-risk tolerance (%)", Group = "Risk", DefaultValue = 10.0, MinValue = 0.0, Step = 1.0,
            Description = "If the broker's minimum lot forces more risk than requested by more than this, " +
                          "the trade is refused rather than taken oversized.")]
        public double OverRiskTolerancePercent { get; set; }

        [Parameter("Poll interval (seconds)", Group = "Risk", DefaultValue = 5, MinValue = 1, MaxValue = 60,
            Description = "How often the bot checks the clock and the risk guards. The bot never acts on " +
                          "raw ticks: cTrader rate-limits algo trading operations and tripping that limit " +
                          "blocks manual trading on the whole account.")]
        public int PollIntervalSeconds { get; set; }

        // -------------------------------------------------------------------- Internal state

        private SessionClock _clock;
        private SessionSchedule _schedule;
        private RangeCalculator _rangeCalculator;
        private BreakoutPlanner _planner;
        private PositionSizer _sizer;
        private RiskGuard _guard;
        private RiskLimits _limits;

        private Bars _rangeBars;
        private AverageTrueRange _atr;

        private DateTime _lastHandledSessionDate = DateTime.MinValue;
        private bool _stopping;

        protected override void OnStart()
        {
            try
            {
                _clock = new SessionClock(SessionClock.ResolveTimeZone(SessionTimeZoneId));
            }
            catch (Exception ex)
            {
                Print("FATAL: " + ex.Message);
                Stop();
                return;
            }

            try
            {
                _schedule = new SessionSchedule(
                    _clock,
                    RangeStartHour, RangeStartMinute,
                    SignalHour, SignalMinute,
                    SessionSchedule.ParseTradingDays(TradingDays));
            }
            catch (Exception ex)
            {
                Print("FATAL: invalid session configuration - " + ex.Message);
                Stop();
                return;
            }

            _rangeCalculator = new RangeCalculator(MinimumRangeBars);

            _planner = new BreakoutPlanner(new BreakoutPlannerSettings
            {
                EntryBufferPips = EntryBufferPips,
                StopMode = StopLossMode,
                FixedStopPips = FixedStopPips,
                AtrMultiplier = AtrMultiplier,
                TargetRMultiple = TargetRMultiple,
                MinRangePips = MinRangePips,
                MaxRangePips = MaxRangePips,
                MinStopDistancePips = ResolveBrokerMinStopPips(),
            });

            _sizer = new PositionSizer();

            _limits = new RiskLimits
            {
                RiskPercentPerTrade = RiskPercent,
                MaxDailyLossPercent = MaxDailyLossPercent,
                MaxDrawdownPercent = MaxDrawdownPercent,
                MaxConcurrentPositions = MaxConcurrentPositions,
                MaxMarginUtilisationPercent = MaxMarginUtilisationPercent,
                TradingEnabled = TradingEnabled,
            };

            _guard = new RiskGuard(_limits);
            _guard.Initialise(Account.Equity, _clock.SessionDateOf(Server.TimeInUtc));

            _rangeBars = MarketData.GetBars(RangeTimeFrame, SymbolName);
            _atr = Indicators.AverageTrueRange(_rangeBars, AtrPeriods, MovingAverageType.Exponential);

            Positions.Opened += OnPositionOpened;

            // Poll on a timer rather than reacting to ticks. Trading operations are rate-limited
            // by cTrader and exceeding the limit locks out manual trading on the account too.
            Timer.Start(TimeSpan.FromSeconds(PollIntervalSeconds));

            Print(
                "London Breakout started on {0}. Session tz={1} (currently UTC{2}). Range {3:00}:{4:00} -> " +
                "signal {5:00}:{6:00} on {7}. Risk {8}%/trade, kill switch {9}.",
                SymbolName,
                _clock.TimeZone.Id,
                _clock.TimeZone.GetUtcOffset(Server.TimeInUtc).ToString(),
                RangeStartHour, RangeStartMinute,
                SignalHour, SignalMinute,
                TradingDays,
                RiskPercent,
                TradingEnabled ? "ON" : "OFF (nothing will be placed)");
        }

        /// <summary>
        /// The main loop. Cheap by design: it usually does nothing but read the clock.
        /// </summary>
        protected override void OnTimer()
        {
            if (_stopping || _guard == null) return;

            var utcNow = Server.TimeInUtc;
            var snapshot = BuildSnapshot(utcNow);

            // Keep the kill switch live so it can be flipped mid-session from the UI.
            _limits.TradingEnabled = TradingEnabled;

            _guard.OnSessionDate(_clock.SessionDateOf(utcNow), snapshot.Equity);

            var observed = _guard.Observe(snapshot);
            if (observed.RequiresFlatten)
            {
                Print("EMERGENCY: " + observed.Reason);
                FlattenEverything();
                _stopping = true;
                Stop();
                return;
            }

            var window = _schedule.ActionableWindow(utcNow);
            if (window == null) return;

            if (window.SessionDate == _lastHandledSessionDate) return;

            // Too late to act on this session's signal (e.g. the bot was restarted at midday).
            if (utcNow > window.SignalTimeUtc.AddMinutes(PlacementGraceMinutes))
            {
                _lastHandledSessionDate = window.SessionDate;
                Print(
                    "Session {0:yyyy-MM-dd}: signal time passed {1:F0} minutes ago, outside the {2}-minute " +
                    "grace window. Skipping.",
                    window.SessionDate,
                    (utcNow - window.SignalTimeUtc).TotalMinutes,
                    PlacementGraceMinutes);
                return;
            }

            HandleSession(window, snapshot, utcNow);
        }

        /// <summary>
        /// Places the straddle for one session. Latches <see cref="_lastHandledSessionDate"/> on
        /// every exit path so a rejected session is never retried on the next tick.
        /// </summary>
        private void HandleSession(SessionWindow window, AccountSnapshot snapshot, DateTime utcNow)
        {
            var gate = _guard.EvaluateEntry(snapshot, newPositionsWanted: 1);
            if (!gate.Allowed)
            {
                _lastHandledSessionDate = window.SessionDate;
                Print("Session {0:yyyy-MM-dd} blocked: {1}", window.SessionDate, gate.Reason);
                return;
            }

            var bars = SnapshotRangeBars();
            var range = _rangeCalculator.Compute(bars, window.RangeStartUtc, window.SignalTimeUtc);
            if (range == null)
            {
                _lastHandledSessionDate = window.SessionDate;
                Print(
                    "Session {0:yyyy-MM-dd}: not enough {1} bars between {2:HH:mm}Z and {3:HH:mm}Z " +
                    "(need {4}). Skipping.",
                    window.SessionDate, RangeTimeFrame, window.RangeStartUtc, window.SignalTimeUtc,
                    MinimumRangeBars);
                return;
            }

            var atrInPrice = _atr.Result.Count > 0 ? _atr.Result.LastValue : 0.0;
            var plan = _planner.BuildPlan(range, Symbol.PipSize, atrInPrice);

            if (!plan.HasLegs)
            {
                _lastHandledSessionDate = window.SessionDate;
                Print("Session {0:yyyy-MM-dd} rejected: {1}", window.SessionDate, plan.RejectionReason);
                return;
            }

            Print(
                "Session {0:yyyy-MM-dd}: range {1:F5} / {2:F5} ({3:F1} pips, {4} bars). " +
                "Buy stop {5:F5}, sell stop {6:F5}.",
                window.SessionDate, range.Low, range.High, range.HeightInPips(Symbol.PipSize), range.BarCount,
                plan.BuyLeg.EntryPrice, plan.SellLeg.EntryPrice);

            var constraints = BuildSymbolConstraints();

            // Both legs share a stop distance by construction, so one sizing call covers both
            // and the risk is identical whichever way price breaks.
            var sizing = _sizer.Calculate(new SizingRequest(
                snapshot.Equity,
                RiskPercent,
                plan.BuyLeg.StopDistance,
                constraints)
            {
                OverRiskTolerance = OverRiskTolerancePercent / 100.0,
            });

            if (!sizing.Accepted)
            {
                _lastHandledSessionDate = window.SessionDate;
                Print("Session {0:yyyy-MM-dd} not sized: {1}", window.SessionDate, sizing.Reason);
                return;
            }

            if (!string.IsNullOrEmpty(sizing.Reason))
                Print("Sizing note: " + sizing.Reason);

            var estimatedMargin = Symbol.GetEstimatedMargin(TradeType.Buy, sizing.VolumeInUnits);
            var marginGate = _guard.EvaluateProjectedMargin(snapshot, estimatedMargin);
            if (!marginGate.Allowed)
            {
                _lastHandledSessionDate = window.SessionDate;
                Print("Session {0:yyyy-MM-dd} blocked on margin: {1}", window.SessionDate, marginGate.Reason);
                return;
            }

            // Latch BEFORE placing. If an order throws we must not retry on the next tick and
            // risk stacking duplicate orders.
            _lastHandledSessionDate = window.SessionDate;

            var expiry = window.SignalTimeUtc.AddHours(OrderExpiryHours);
            if (expiry <= utcNow) expiry = utcNow.AddMinutes(5);

            Print(
                "Placing straddle: {0} units, risking {1:F2} {2} ({3:F2}% of {4:F2}), expiry {5:yyyy-MM-dd HH:mm}Z",
                sizing.VolumeInUnits, sizing.ActualRiskAmount, Account.Asset.Name,
                sizing.ActualRiskAmount / snapshot.Equity * 100.0, snapshot.Equity, expiry);

            PlaceLeg(plan.BuyLeg, sizing.VolumeInUnits, expiry);
            PlaceLeg(plan.SellLeg, sizing.VolumeInUnits, expiry);
        }

        /// <summary>
        /// Places one leg with its protection attached at submission time.
        ///
        /// The stop loss, take profit and expiry are all passed as ORDER ATTRIBUTES rather than
        /// applied afterwards in a tick handler. They then live on the broker's servers: if this
        /// process is killed, the machine loses power or the platform is closed, the protection
        /// is still there. A stop that only exists inside a running bot is not a stop.
        ///
        /// The expiry matters for a second reason specific to this straddle. If one leg fills
        /// and the bot dies before it can cancel the other, the surviving pending order would
        /// otherwise sit there indefinitely and could open an unwanted opposite position days
        /// later. The server-side expiry makes that orphan clean itself up.
        /// </summary>
        private void PlaceLeg(BreakoutLeg leg, double volumeInUnits, DateTime expiryUtc)
        {
            var tradeType = leg.IsBuy ? TradeType.Buy : TradeType.Sell;

            var entry = RoundToTick(leg.EntryPrice);
            var stopLoss = RoundToTick(leg.StopLossPrice);
            var takeProfit = RoundToTick(leg.TakeProfitPrice);

            // ProtectionType.Absolute means stopLoss/takeProfit are PRICES, not pip distances.
            // Preferred over the pips overload because the levels come straight from the range
            // geometry: expressing them as rounded pip distances would nudge the stop off the
            // actual support/resistance line it is meant to sit on.
            var result = PlaceStopOrder(
                tradeType,
                SymbolName,
                volumeInUnits,
                entry,
                OrderLabel,
                stopLoss,
                takeProfit,
                ProtectionType.Absolute,
                expiryUtc,
                BuildComment(leg));

            if (result.IsSuccessful)
            {
                Print("  {0} placed @{1} SL {2} TP {3} ({4:F1} pip stop)",
                    leg.IsBuy ? "BUY STOP" : "SELL STOP", entry, stopLoss, takeProfit,
                    leg.StopDistanceInPips(Symbol.PipSize));
            }
            else
            {
                Print("  FAILED to place {0} @{1}: {2}",
                    leg.IsBuy ? "BUY STOP" : "SELL STOP", entry, result.Error);
            }
        }

        /// <summary>
        /// Snaps a price onto the symbol's tick grid. Range highs and lows come off the feed
        /// already aligned, but the entry buffer and the R-multiple target are arithmetic
        /// results that can land between ticks, which the server rejects.
        /// </summary>
        private double RoundToTick(double price)
        {
            var tickSize = Symbol.TickSize;
            if (tickSize <= 0) return Math.Round(price, Symbol.Digits);
            return Math.Round(Math.Round(price / tickSize) * tickSize, Symbol.Digits);
        }

        private string BuildComment(BreakoutLeg leg)
        {
            return string.Format("LBO {0} R{1:F1}", leg.IsBuy ? "up" : "dn", TargetRMultiple);
        }

        /// <summary>
        /// Manual OCO.
        ///
        /// VERIFIED: cAlgo.API 1.0.19 has no native one-cancels-other facility. The PendingOrder
        /// interface exposes no linked-order, OCO-group or sibling property, and there is no
        /// PlaceStopOrder overload that accepts one -- checked by reflecting over the shipped
        /// cAlgo.API.dll. Cancelling the sibling in code is therefore the only option, and it is
        /// exactly why the server-side expiry above is not optional: this handler only runs if
        /// the bot is alive.
        /// </summary>
        private void OnPositionOpened(PositionOpenedEventArgs args)
        {
            var position = args.Position;
            if (position == null) return;
            if (!string.Equals(position.Label, OrderLabel, StringComparison.Ordinal)) return;
            if (!string.Equals(position.SymbolName, SymbolName, StringComparison.Ordinal)) return;

            if (!CancelSiblingOnFill) return;

            // Cancel our remaining pending orders on this symbol -- i.e. the other leg.
            var toCancel = new List<PendingOrder>();
            foreach (var order in PendingOrders)
            {
                if (!string.Equals(order.Label, OrderLabel, StringComparison.Ordinal)) continue;
                if (!string.Equals(order.SymbolName, SymbolName, StringComparison.Ordinal)) continue;
                toCancel.Add(order);
            }

            foreach (var order in toCancel)
            {
                var result = order.Cancel();
                Print("OCO: {0} sibling {1} order @{2:F5}",
                    result.IsSuccessful ? "cancelled" : "FAILED to cancel",
                    order.TradeType, order.TargetPrice);
            }
        }

        protected override void OnStop()
        {
            _stopping = true;
            Positions.Opened -= OnPositionOpened;
            Timer.Stop();

            if (_guard != null && _guard.IsHalted)
                Print("Stopped after halt: " + _guard.HaltReason);
            else
                Print("London Breakout stopped. Open positions and pending orders were left in place; " +
                      "their server-side stops and expiries remain active.");
        }

        // ------------------------------------------------------------------------- Helpers

        private AccountSnapshot BuildSnapshot(DateTime utcNow)
        {
            var ourPositions = Positions.FindAll(OrderLabel, SymbolName);
            return new AccountSnapshot(
                Account.Equity,
                Account.Balance,
                Account.Margin,
                ourPositions.Length,
                utcNow);
        }

        private SymbolConstraints BuildSymbolConstraints()
        {
            return new SymbolConstraints(
                Symbol.VolumeInUnitsMin,
                Symbol.VolumeInUnitsMax,
                Symbol.VolumeInUnitsStep,
                Symbol.PipSize,
                Symbol.PipValue);
        }

        /// <summary>
        /// Copies the range bars into cTrader-free structs for the pure calculator. Only the
        /// bars that could plausibly matter are copied, so this stays cheap on a long history.
        /// </summary>
        private IReadOnlyList<PriceBar> SnapshotRangeBars()
        {
            var result = new List<PriceBar>();
            var count = _rangeBars.Count;

            // A range never spans more than a day; cap the copy generously rather than walking
            // the whole series.
            var maxBars = Math.Min(count, 5000);

            for (var i = count - maxBars; i < count; i++)
            {
                if (i < 0) continue;
                var bar = _rangeBars[i];
                result.Add(new PriceBar(bar.OpenTime, bar.Open, bar.High, bar.Low, bar.Close));
            }

            return result;
        }

        /// <summary>
        /// The broker's minimum stop distance, normalised to pips. cTrader reports it either in
        /// pips or as an absolute price depending on the symbol, so the unit has to be checked.
        /// </summary>
        private double ResolveBrokerMinStopPips()
        {
            try
            {
                var raw = Symbol.MinStopLossDistance;
                if (raw <= 0) return 0.0;

                return Symbol.MinDistanceType == SymbolMinDistanceType.Pips
                    ? raw
                    : raw / Symbol.PipSize;
            }
            catch
            {
                return 0.0;
            }
        }

        private void FlattenEverything()
        {
            foreach (var order in PendingOrders)
            {
                if (!string.Equals(order.Label, OrderLabel, StringComparison.Ordinal)) continue;
                order.Cancel();
            }

            foreach (var position in Positions.FindAll(OrderLabel, SymbolName))
            {
                var result = position.Close();
                Print("Flatten: {0} position {1}", result.IsSuccessful ? "closed" : "FAILED to close", position.Id);
            }
        }
    }
}
