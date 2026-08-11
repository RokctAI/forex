using System;

namespace LondonBreakout.Core.Risk
{
    /// <summary>What the guard decided, and why.</summary>
    public sealed class GuardDecision
    {
        private GuardDecision(bool allowed, bool requiresFlatten, bool requiresHalt, string reason)
        {
            Allowed = allowed;
            RequiresFlatten = requiresFlatten;
            RequiresHalt = requiresHalt;
            Reason = reason;
        }

        public bool Allowed { get; }

        /// <summary>The caller must close all open positions immediately.</summary>
        public bool RequiresFlatten { get; }

        /// <summary>The caller must stop the bot; a human has to restart it.</summary>
        public bool RequiresHalt { get; }

        public string Reason { get; }

        public static GuardDecision Allow() => new GuardDecision(true, false, false, "OK");

        public static GuardDecision Block(string reason)
            => new GuardDecision(false, false, false, reason);

        public static GuardDecision Emergency(string reason)
            => new GuardDecision(false, true, true, reason);

        public override string ToString() => Allowed ? "ALLOW" : $"BLOCK: {Reason}";
    }

    /// <summary>
    /// The account-level risk gate. It owns the equity peak, the daily loss baseline and the
    /// halt latch, and it is the only thing that decides whether an entry may proceed.
    ///
    /// The strategy must call <see cref="Observe"/> on every timer tick (so drawdown is tracked
    /// continuously, not just at entry time) and <see cref="EvaluateEntry"/> immediately before
    /// every order placement.
    ///
    /// Pure and cTrader-free.
    /// </summary>
    public sealed class RiskGuard
    {
        private readonly RiskLimits _limits;

        private double _equityPeak;
        private double _dayStartEquity;
        private DateTime _currentSessionDate = DateTime.MinValue;
        private bool _initialised;

        public RiskGuard(RiskLimits limits)
        {
            _limits = limits ?? throw new ArgumentNullException(nameof(limits));
        }

        public bool IsHalted { get; private set; }
        public string HaltReason { get; private set; }
        public double EquityPeak => _equityPeak;
        public double DayStartEquity => _dayStartEquity;
        public DateTime CurrentSessionDate => _currentSessionDate;

        /// <summary>Whether the daily loss limit has already tripped for the current session.</summary>
        public bool DailyLossBreached { get; private set; }

        /// <summary>
        /// Seeds the peak and the daily baseline. Call once from OnStart.
        /// </summary>
        public void Initialise(double equity, DateTime sessionDate)
        {
            _equityPeak = equity;
            _dayStartEquity = equity;
            _currentSessionDate = sessionDate.Date;
            _initialised = true;
            DailyLossBreached = false;
        }

        /// <summary>
        /// Rolls the daily baseline when the session date changes. Idempotent: calling it
        /// repeatedly within the same session does nothing, so it is safe on every tick.
        /// </summary>
        public void OnSessionDate(DateTime sessionDate, double equity)
        {
            if (!_initialised)
            {
                Initialise(equity, sessionDate);
                return;
            }

            if (sessionDate.Date == _currentSessionDate) return;

            _currentSessionDate = sessionDate.Date;
            _dayStartEquity = equity;
            DailyLossBreached = false;
        }

        /// <summary>
        /// Continuous monitoring. Updates the equity peak and evaluates the catastrophic
        /// drawdown limit. Returns an emergency decision when the account must be flattened.
        /// </summary>
        public GuardDecision Observe(AccountSnapshot snapshot)
        {
            if (snapshot == null) throw new ArgumentNullException(nameof(snapshot));

            if (!_initialised)
                Initialise(snapshot.Equity, snapshot.UtcNow.Date);

            if (snapshot.Equity > _equityPeak)
                _equityPeak = snapshot.Equity;

            if (IsHalted)
                return GuardDecision.Block(HaltReason);

            if (_limits.MaxDrawdownPercent > 0 && _equityPeak > 0)
            {
                var drawdownPercent = ((_equityPeak - snapshot.Equity) / _equityPeak) * 100.0;
                if (drawdownPercent >= _limits.MaxDrawdownPercent)
                {
                    var reason =
                        $"Max drawdown breached: equity {snapshot.Equity:F2} is {drawdownPercent:F2}% below " +
                        $"the peak of {_equityPeak:F2} (limit {_limits.MaxDrawdownPercent:F2}%). " +
                        "Flattening and halting; a manual restart is required.";
                    Halt(reason);
                    return GuardDecision.Emergency(reason);
                }
            }

            if (_limits.MaxDailyLossPercent > 0 && _dayStartEquity > 0 && !DailyLossBreached)
            {
                var dayLossPercent = ((_dayStartEquity - snapshot.Equity) / _dayStartEquity) * 100.0;
                if (dayLossPercent >= _limits.MaxDailyLossPercent)
                {
                    DailyLossBreached = true;
                }
            }

            return GuardDecision.Allow();
        }

        /// <summary>
        /// The pre-entry gate. Consulted immediately before every order placement.
        /// </summary>
        /// <param name="newPositionsWanted">
        /// How many positions this entry could open. The straddle places two pending orders but
        /// only one is expected to fill, so the bot passes 1 -- the OCO cancel plus this cap are
        /// what keep that true.
        /// </param>
        public GuardDecision EvaluateEntry(AccountSnapshot snapshot, int newPositionsWanted = 1)
        {
            if (snapshot == null) throw new ArgumentNullException(nameof(snapshot));

            if (IsHalted)
                return GuardDecision.Block($"Bot is halted: {HaltReason}");

            // The kill switch is checked first and unconditionally.
            if (!_limits.TradingEnabled)
                return GuardDecision.Block("Kill switch is engaged (TradingEnabled = false).");

            var observed = Observe(snapshot);
            if (!observed.Allowed) return observed;

            if (DailyLossBreached)
            {
                return GuardDecision.Block(
                    $"Daily loss limit of {_limits.MaxDailyLossPercent:F2}% already breached for " +
                    $"{_currentSessionDate:yyyy-MM-dd}; no new positions until the next session.");
            }

            if (snapshot.Equity <= 0)
                return GuardDecision.Block($"Equity is {snapshot.Equity:F2}.");

            if (_limits.MaxConcurrentPositions > 0 &&
                snapshot.OpenPositions + newPositionsWanted > _limits.MaxConcurrentPositions)
            {
                return GuardDecision.Block(
                    $"Would exceed MaxConcurrentPositions ({_limits.MaxConcurrentPositions}): " +
                    $"{snapshot.OpenPositions} already open.");
            }

            if (_limits.MaxMarginUtilisationPercent > 0 &&
                snapshot.MarginUtilisationPercent >= _limits.MaxMarginUtilisationPercent)
            {
                return GuardDecision.Block(
                    $"Margin utilisation {snapshot.MarginUtilisationPercent:F1}% is at or above the " +
                    $"{_limits.MaxMarginUtilisationPercent:F1}% ceiling.");
            }

            return GuardDecision.Allow();
        }

        /// <summary>
        /// Checks whether committing <paramref name="estimatedMargin"/> more margin would break
        /// the utilisation ceiling. Separate from <see cref="EvaluateEntry"/> because the margin
        /// estimate is only known after the position has been sized.
        /// </summary>
        public GuardDecision EvaluateProjectedMargin(AccountSnapshot snapshot, double estimatedMargin)
        {
            if (snapshot == null) throw new ArgumentNullException(nameof(snapshot));
            if (_limits.MaxMarginUtilisationPercent <= 0) return GuardDecision.Allow();
            if (snapshot.Equity <= 0) return GuardDecision.Block("Equity is not positive.");

            var projected = ((snapshot.MarginUsed + estimatedMargin) / snapshot.Equity) * 100.0;
            if (projected > _limits.MaxMarginUtilisationPercent)
            {
                return GuardDecision.Block(
                    $"Projected margin utilisation {projected:F1}% would exceed the " +
                    $"{_limits.MaxMarginUtilisationPercent:F1}% ceiling.");
            }

            return GuardDecision.Allow();
        }

        public void Halt(string reason)
        {
            IsHalted = true;
            HaltReason = reason;
        }
    }
}
