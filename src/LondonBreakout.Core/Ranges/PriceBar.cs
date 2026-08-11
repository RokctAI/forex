using System;

namespace LondonBreakout.Core.Ranges
{
    /// <summary>
    /// A cTrader-free view of an OHLC bar. The bot maps <c>cAlgo.API.Bar</c> onto this so the
    /// range logic can be unit-tested without the trading assembly.
    /// </summary>
    /// <remarks>
    /// <see cref="OpenTimeUtc"/> must be UTC. The bot guarantees this by declaring itself as a
    /// UTC robot, which makes cTrader express all bar open times in UTC.
    /// </remarks>
    public readonly struct PriceBar
    {
        public PriceBar(DateTime openTimeUtc, double open, double high, double low, double close)
        {
            OpenTimeUtc = DateTime.SpecifyKind(openTimeUtc, DateTimeKind.Utc);
            Open = open;
            High = high;
            Low = low;
            Close = close;
        }

        public DateTime OpenTimeUtc { get; }
        public double Open { get; }
        public double High { get; }
        public double Low { get; }
        public double Close { get; }

        public override string ToString()
            => $"{OpenTimeUtc:yyyy-MM-dd HH:mm}Z O={Open} H={High} L={Low} C={Close}";
    }
}
