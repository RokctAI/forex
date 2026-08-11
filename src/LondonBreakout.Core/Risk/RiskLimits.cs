namespace LondonBreakout.Core.Risk
{
    /// <summary>
    /// The hard ceilings the strategy is not allowed to cross. Every value is a percentage of
    /// equity unless stated otherwise; zero disables the individual check.
    /// </summary>
    public sealed class RiskLimits
    {
        /// <summary>Risk budget for a single trade, as a percentage of equity.</summary>
        public double RiskPercentPerTrade { get; set; } = 0.5;

        /// <summary>
        /// Once the day's realised+unrealised loss reaches this percentage of the equity the
        /// day started at, no new positions are opened until the next session. Existing
        /// positions keep their server-side stops and are left alone.
        /// </summary>
        public double MaxDailyLossPercent { get; set; } = 2.0;

        /// <summary>
        /// Measured from the highest equity ever seen by this bot instance, not from the
        /// starting balance. Breaching it flattens everything and halts permanently -- a
        /// deliberate manual restart is required, because a drawdown this size usually means
        /// the market regime changed or something is wrong with the setup, and neither is
        /// fixed by letting the bot keep trading.
        /// </summary>
        public double MaxDrawdownPercent { get; set; } = 10.0;

        /// <summary>Cap on simultaneously open positions belonging to this bot.</summary>
        public int MaxConcurrentPositions { get; set; } = 1;

        /// <summary>
        /// Refuse new entries when margin already in use exceeds this percentage of equity.
        /// Keeps a buffer between the bot and a margin call.
        /// </summary>
        public double MaxMarginUtilisationPercent { get; set; } = 20.0;

        /// <summary>
        /// Master kill switch. When false the strategy places nothing, regardless of every
        /// other condition. Exposed as a bot parameter so it can be flipped from the cTrader UI
        /// without detaching the instance.
        /// </summary>
        public bool TradingEnabled { get; set; } = true;
    }
}
