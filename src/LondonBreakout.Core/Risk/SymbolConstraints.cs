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

        /// <summary>Price increment of one pip, e.g. 0.0001 on EURUSD, 0.01 on USDJPY.</summary>
        public double PipSize { get; }

        /// <summary>
        /// Account-currency value of a one-pip move on ONE unit of volume. This is cTrader's
        /// <c>Symbol.PipValue</c>, which already handles cross-currency conversion back to the
        /// deposit currency -- which is exactly why we take it as an input rather than trying to
        /// recompute it.
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
