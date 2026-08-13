using System;

namespace LondonBreakout.Core.Planning
{
    /// <summary>How a configured distance is expressed.</summary>
    public enum DistanceMode
    {
        /// <summary>
        /// A fixed number of pips. Simple and predictable, but a value tuned on one symbol is
        /// wrong on another -- see <see cref="DistanceSpec"/>.
        /// </summary>
        Pips = 0,

        /// <summary>
        /// Default. A multiple of the reference ATR, so the distance scales with the symbol's
        /// own volatility and one parameter set is sane on both GBPJPY and GBPUSD.
        /// </summary>
        AtrMultiple = 1,
    }

    /// <summary>
    /// A distance that can be expressed either in pips or as a multiple of ATR, and is resolved
    /// to a price distance at the point of use.
    ///
    /// WHY THIS TYPE EXISTS
    /// --------------------
    /// The strategy runs on two symbols that are not interchangeable:
    ///
    ///   * GBPJPY is quoted to 3 decimals, so one pip is 0.01.
    ///   * GBPUSD is quoted to 5 decimals, so one pip is 0.0001.
    ///
    /// The pip *size* difference is handled everywhere by reading the symbol's own pip size
    /// rather than assuming a constant, so a "20 pip" distance is correctly 0.20 on GBPJPY and
    /// 0.0020 on GBPUSD. That part is a units problem and it is solved.
    ///
    /// The second difference is not a units problem and cannot be solved by arithmetic: GBPJPY's
    /// typical daily range is roughly double GBPUSD's. So "20 pips" is a materially *tighter*
    /// distance on GBPJPY than the same number is on GBPUSD, in the only sense that matters --
    /// how likely price is to travel it. Any fixed-pip buffer, minimum-range floor or stop
    /// distance tuned on one symbol is therefore mis-scaled on the other even when the pip maths
    /// is perfect.
    ///
    /// Expressing these distances as multiples of the symbol's own ATR removes the problem: the
    /// same multiplier means the same thing, in volatility terms, on both symbols. That is why
    /// <see cref="DistanceMode.AtrMultiple"/> is the default. Fixed pips remains available for
    /// anyone who wants an exact, symbol-specific number.
    /// </summary>
    public sealed class DistanceSpec
    {
        public DistanceSpec(DistanceMode mode, double pips, double atrMultiple)
        {
            Mode = mode;
            Pips = pips;
            AtrMultiple = atrMultiple;
        }

        public DistanceMode Mode { get; }

        /// <summary>Used when <see cref="Mode"/> is <see cref="DistanceMode.Pips"/>.</summary>
        public double Pips { get; }

        /// <summary>Used when <see cref="Mode"/> is <see cref="DistanceMode.AtrMultiple"/>.</summary>
        public double AtrMultiple { get; }

        public static DistanceSpec FromPips(double pips) => new DistanceSpec(DistanceMode.Pips, pips, 0.0);

        public static DistanceSpec FromAtr(double multiple) => new DistanceSpec(DistanceMode.AtrMultiple, 0.0, multiple);

        /// <summary>
        /// Resolves this distance to price units.
        /// </summary>
        /// <param name="pipSize">The symbol's own pip size (0.01 on GBPJPY, 0.0001 on GBPUSD).</param>
        /// <param name="atrInPrice">
        /// The reference ATR in price units. Only consulted in ATR mode; pass 0 when unavailable.
        /// </param>
        /// <param name="unavailableReason">
        /// Set when the distance cannot be resolved -- currently only when ATR mode is selected
        /// and no ATR is available yet. Callers reject the session rather than falling back to a
        /// pip default, because a silent fallback is how a distance tuned for one symbol ends up
        /// applied to the other.
        /// </param>
        /// <returns>The distance in price units, or 0 when <paramref name="unavailableReason"/> is set.</returns>
        public double ResolveToPrice(double pipSize, double atrInPrice, string label, out string unavailableReason)
        {
            unavailableReason = null;

            if (pipSize <= 0)
                throw new ArgumentOutOfRangeException(nameof(pipSize), pipSize, "Pip size must be positive.");

            switch (Mode)
            {
                case DistanceMode.Pips:
                    if (Pips < 0)
                    {
                        unavailableReason = $"{label} is {Pips} pips; must not be negative.";
                        return 0;
                    }
                    return Pips * pipSize;

                case DistanceMode.AtrMultiple:
                    if (AtrMultiple < 0)
                    {
                        unavailableReason = $"{label} ATR multiple is {AtrMultiple}; must not be negative.";
                        return 0;
                    }
                    if (AtrMultiple > 0 && atrInPrice <= 0)
                    {
                        unavailableReason =
                            $"{label} is configured as an ATR multiple but no ATR is available yet " +
                            "(needs more history); skipping this session.";
                        return 0;
                    }
                    return atrInPrice * AtrMultiple;

                default:
                    unavailableReason = $"Unknown distance mode '{Mode}' for {label}.";
                    return 0;
            }
        }

        public override string ToString()
            => Mode == DistanceMode.Pips ? $"{Pips:F1} pips" : $"{AtrMultiple:F3}x ATR";
    }
}
