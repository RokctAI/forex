using System;

namespace LondonBreakout.Core.Ranges
{
    /// <summary>
    /// The pre-session range: the high (resistance) and low (support) recorded between the
    /// range start and the signal time.
    /// </summary>
    public sealed class OpeningRange
    {
        public OpeningRange(double high, double low, int barCount, DateTime startUtc, DateTime endUtc)
        {
            if (high < low)
                throw new ArgumentException($"Range high ({high}) cannot be below range low ({low}).", nameof(high));
            if (barCount <= 0)
                throw new ArgumentOutOfRangeException(nameof(barCount), barCount, "A range needs at least one bar.");

            High = high;
            Low = low;
            BarCount = barCount;
            StartUtc = startUtc;
            EndUtc = endUtc;
        }

        /// <summary>Resistance: the highest traded price in the range window.</summary>
        public double High { get; }

        /// <summary>Support: the lowest traded price in the range window.</summary>
        public double Low { get; }

        /// <summary>How many bars contributed. Used to reject thin/gappy data.</summary>
        public int BarCount { get; }

        public DateTime StartUtc { get; }
        public DateTime EndUtc { get; }

        /// <summary>Range height in price terms.</summary>
        public double Height => High - Low;

        public double HeightInPips(double pipSize)
        {
            if (pipSize <= 0)
                throw new ArgumentOutOfRangeException(nameof(pipSize), pipSize, "Pip size must be positive.");
            return Height / pipSize;
        }

        /// <summary>Midpoint, handy for logging and chart annotation.</summary>
        public double Midpoint => (High + Low) / 2.0;

        public override string ToString()
            => $"Range [{Low} .. {High}] height={Height} from {BarCount} bars ({StartUtc:HH:mm}Z-{EndUtc:HH:mm}Z)";
    }
}
