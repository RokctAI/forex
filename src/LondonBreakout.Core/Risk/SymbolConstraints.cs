using System;

namespace LondonBreakout.Core.Risk
{
    /// <summary>
    /// The broker's volume rules for one symbol, lifted out of <c>cAlgo.API.Internals.Symbol</c>
    /// so the sizing maths can be tested without the trading assembly.
    /// </summary>
    public sealed class SymbolConstraints
    {
        public SymbolConstraints(
            double volumeInUnitsMin,
            double volumeInUnitsMax,
            double volumeInUnitsStep,
            double pipSize,
            double pipValuePerUnit)
        {
            if (volumeInUnitsMin <= 0)
                throw new ArgumentOutOfRangeException(nameof(volumeInUnitsMin), volumeInUnitsMin, "Must be positive.");
            if (volumeInUnitsMax < volumeInUnitsMin)
                throw new ArgumentOutOfRangeException(nameof(volumeInUnitsMax), volumeInUnitsMax, "Max below min.");
            if (volumeInUnitsStep <= 0)
                throw new ArgumentOutOfRangeException(nameof(volumeInUnitsStep), volumeInUnitsStep, "Must be positive.");
            if (pipSize <= 0)
                throw new ArgumentOutOfRangeException(nameof(pipSize), pipSize, "Must be positive.");
            if (pipValuePerUnit <= 0)
                throw new ArgumentOutOfRangeException(nameof(pipValuePerUnit), pipValuePerUnit, "Must be positive.");

            VolumeInUnitsMin = volumeInUnitsMin;
            VolumeInUnitsMax = volumeInUnitsMax;
            VolumeInUnitsStep = volumeInUnitsStep;
            PipSize = pipSize;
            PipValuePerUnit = pipValuePerUnit;
        }

        public double VolumeInUnitsMin { get; }
        public double VolumeInUnitsMax { get; }
        public double VolumeInUnitsStep { get; }

        /// <summary>
        /// Price increment of one pip. Read from the symbol, never assumed: it is 0.0001 on
        /// GBPUSD (5-digit quote) and 0.01 on GBPJPY (3-digit quote). Code that hardcodes 0.0001
        /// is wrong by a factor of 100 on every JPY-quoted pair.
        /// </summary>
        public double PipSize { get; }

        /// <summary>
        /// Account-currency value of a one-pip move on ONE unit of volume. This is cTrader's
        /// <c>Symbol.PipValue</c>, taken as an input rather than recomputed.
        ///
        /// WHY THIS MUST NOT BE HAND-ROLLED
        /// --------------------------------
        /// A pip value is only in account currency after a conversion whose rate the bot does
        /// not have. Take the live case: GBPJPY traded from a ZAR (or USD) account.
        ///
        ///   * A one-pip move on GBPJPY earns JPY, because JPY is the QUOTE currency. One pip on
        ///     one unit is 0.01 JPY.
        ///   * Turning that into account currency needs the current JPY/ZAR (or JPY/USD) rate.
        ///     That rate moves independently of GBPJPY, so the account-currency value of a pip
        ///     drifts even on a day GBPJPY does not move at all.
        ///   * GBPUSD from the same ZAR account has the same shape with a different leg: pips
        ///     are earned in USD and converted at USD/ZAR.
        ///
        /// Inside a cBot this is already solved: <c>Symbol.PipValue</c> is quoted in the deposit
        /// currency and cTrader keeps the conversion leg current. So the correct thing to do --
        /// and what this type does -- is take that number and multiply, never reconstruct it.
        ///
        /// This is called out because it is precisely the step a port to an external market-data
        /// API would get wrong. Such an API typically hands back a raw quote and nothing else; a
        /// naive port multiplies stop distance by 0.0001, or by a contract size, and produces
        /// position sizes that are wrong by whatever JPY/ZAR happens to be -- roughly two orders
        /// of magnitude, and silently, because the resulting number still looks like a volume.
        /// Any such port must source a live conversion rate and apply it here explicitly.
        /// </summary>
        public double PipValuePerUnit { get; }

        /// <summary>
        /// Rounds a raw volume DOWN onto the broker's lot grid. Down, not nearest: rounding up
        /// would push realised risk above the requested percentage, and the whole point of this
        /// layer is that the requested percentage is an upper bound.
        /// </summary>
        public double RoundDownToStep(double rawVolume)
        {
            if (rawVolume <= VolumeInUnitsMin) return VolumeInUnitsMin;

            var stepsAboveMin = Math.Floor((rawVolume - VolumeInUnitsMin) / VolumeInUnitsStep);
            var rounded = VolumeInUnitsMin + (stepsAboveMin * VolumeInUnitsStep);

            // Guard against floating point leaving us a hair under a legitimate step.
            if (rounded + (VolumeInUnitsStep * 1e-9) < rawVolume &&
                rounded + VolumeInUnitsStep <= rawVolume + (VolumeInUnitsStep * 1e-9))
            {
                rounded += VolumeInUnitsStep;
            }

            return Math.Min(rounded, VolumeInUnitsMax);
        }
    }
}
