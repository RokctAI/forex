using System;

namespace LondonBreakout.Core.Sessions
{
    /// <summary>
    /// One trading session's boundaries, resolved to UTC instants.
    /// The range is the half-open interval [RangeStartUtc, SignalTimeUtc).
    /// </summary>
    public sealed class SessionWindow
    {
        public SessionWindow(DateTime sessionDate, DateTime rangeStartUtc, DateTime signalTimeUtc)
        {
            if (signalTimeUtc <= rangeStartUtc)
            {
                throw new ArgumentException(
                    $"Signal time ({signalTimeUtc:o}) must be after range start ({rangeStartUtc:o}).",
                    nameof(signalTimeUtc));
            }

            SessionDate = sessionDate.Date;
            RangeStartUtc = rangeStartUtc;
            SignalTimeUtc = signalTimeUtc;
        }

        /// <summary>The session-local calendar date this window belongs to.</summary>
        public DateTime SessionDate { get; }

        /// <summary>Inclusive start of the range-building period.</summary>
        public DateTime RangeStartUtc { get; }

        /// <summary>
        /// Exclusive end of the range-building period, and the moment orders may be placed.
        /// Bars that open at or after this instant do not contribute to the range.
        /// </summary>
        public DateTime SignalTimeUtc { get; }

        public TimeSpan Duration => SignalTimeUtc - RangeStartUtc;

        public bool IsRangeComplete(DateTime utcNow) => utcNow >= SignalTimeUtc;

        public override string ToString()
            => $"{SessionDate:yyyy-MM-dd}: range {RangeStartUtc:HH:mm}Z -> signal {SignalTimeUtc:HH:mm}Z";
    }
}
