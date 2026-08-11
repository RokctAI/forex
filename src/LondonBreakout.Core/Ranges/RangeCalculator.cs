using System;
using System.Collections.Generic;

namespace LondonBreakout.Core.Ranges
{
    /// <summary>
    /// Computes the pre-session high/low from a bar series. Pure and cTrader-free.
    /// </summary>
    public sealed class RangeCalculator
    {
        private readonly int _minimumBars;

        /// <param name="minimumBars">
        /// Reject a range built from fewer bars than this. Guards against holidays, feed gaps
        /// and the bot being started mid-session, all of which would otherwise produce an
        /// artificially narrow range -- and a narrow range means a tight stop, which means the
        /// position sizer asks for a very large position. A bad range is a sizing hazard, not
        /// just a bad signal.
        /// </param>
        public RangeCalculator(int minimumBars = 1)
        {
            if (minimumBars < 1)
                throw new ArgumentOutOfRangeException(nameof(minimumBars), minimumBars, "Need at least one bar.");
            _minimumBars = minimumBars;
        }

        public int MinimumBars => _minimumBars;

        /// <summary>
        /// Highest high and lowest low over bars whose open time falls in
        /// [startUtc, endUtcExclusive).
        ///
        /// The interval is half-open on purpose. With the default settings the range covers
        /// 00:00 up to 09:00 London and the bar that OPENS at 09:00 is excluded: it belongs to
        /// the post-signal period the bot is trying to trade, so letting it into the range
        /// would leak future information into the levels (a look-ahead bug that flatters
        /// backtests and does nothing live).
        /// </summary>
        /// <returns>The range, or null if too few bars fall in the window.</returns>
        public OpeningRange Compute(IReadOnlyList<PriceBar> bars, DateTime startUtc, DateTime endUtcExclusive)
        {
            if (bars == null) throw new ArgumentNullException(nameof(bars));
            if (endUtcExclusive <= startUtc)
                throw new ArgumentException("Range end must be after range start.", nameof(endUtcExclusive));

            var high = double.NegativeInfinity;
            var low = double.PositiveInfinity;
            var count = 0;

            for (var i = 0; i < bars.Count; i++)
            {
                var bar = bars[i];
                if (bar.OpenTimeUtc < startUtc) continue;
                if (bar.OpenTimeUtc >= endUtcExclusive) continue;

                if (bar.High > high) high = bar.High;
                if (bar.Low < low) low = bar.Low;
                count++;
            }

            if (count < _minimumBars) return null;

            return new OpeningRange(high, low, count, startUtc, endUtcExclusive);
        }
    }
}
