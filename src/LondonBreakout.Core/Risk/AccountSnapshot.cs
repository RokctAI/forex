using System;

namespace LondonBreakout.Core.Risk
{
    /// <summary>
    /// An immutable read of account state at one instant, decoupled from
    /// <c>cAlgo.API.Internals.IAccount</c> so the guards can be tested.
    /// </summary>
    public sealed class AccountSnapshot
    {
        public AccountSnapshot(
            double equity,
            double balance,
            double marginUsed,
            int openPositions,
            DateTime utcNow)
        {
            Equity = equity;
            Balance = balance;
            MarginUsed = marginUsed;
            OpenPositions = openPositions;
            UtcNow = utcNow;
        }

        public double Equity { get; }
        public double Balance { get; }
        public double MarginUsed { get; }
        public int OpenPositions { get; }
        public DateTime UtcNow { get; }

        /// <summary>
        /// Margin in use as a percentage of equity. Reported rather than the more common
        /// "margin level" because a ceiling is easier to reason about than a floor when the
        /// goal is "don't commit more than X% of the account".
        /// </summary>
        public double MarginUtilisationPercent
            => Equity <= 0 ? double.PositiveInfinity : (MarginUsed / Equity) * 100.0;
    }
}
