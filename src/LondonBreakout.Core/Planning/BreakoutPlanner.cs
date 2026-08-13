using System;
using LondonBreakout.Core.Ranges;

namespace LondonBreakout.Core.Planning
{
    /// <summary>Configuration for turning a range into a pair of pending orders.</summary>
    public sealed class BreakoutPlannerSettings
    {
        /// <summary>
        /// How far beyond the range edge the entry sits. A breakout order placed exactly on the
        /// line gets triggered by the spread wobbling around the level; a small buffer means
        /// price has to actually clear the line.
        ///
        /// Defaults to an ATR multiple rather than a fixed pip count so that one setting is
        /// sane on both GBPJPY and GBPUSD. See <see cref="DistanceSpec"/> for why a fixed pip
        /// buffer cannot be right on both.
        /// </summary>
        public DistanceSpec EntryBuffer { get; set; } = DistanceSpec.FromAtr(0.05);

        public StopMode StopMode { get; set; } = StopMode.OppositeRangeSide;

        /// <summary>Used when <see cref="StopMode"/> is <see cref="StopMode.FixedPips"/>.</summary>
        public double FixedStopPips { get; set; } = 20.0;

        /// <summary>
        /// Used when <see cref="StopMode"/> is <see cref="StopMode.AtrMultiple"/>. A multiple of
        /// the same reference ATR every other ATR-relative setting uses -- which is a DAILY ATR
        /// by default, not an intraday one, so sane values here are well below 1.
        /// </summary>
        public double AtrMultiplier { get; set; } = 0.5;

        /// <summary>Target distance as a multiple of the stop distance. 1.0 = a 1:1 payoff.</summary>
        public double TargetRMultiple { get; set; } = 1.0;

        /// <summary>
        /// Reject sessions whose range is narrower than this. A very tight range yields a very
        /// tight stop, and the position sizer would respond by asking for an enormous position.
        /// This is a risk control, not a signal filter.
        ///
        /// Volatility-relative by default for the same reason as the entry buffer: a 5-pip floor
        /// is a meaningful filter on GBPUSD and almost no filter at all on GBPJPY, whose typical
        /// daily range is roughly double.
        /// </summary>
        public DistanceSpec MinRange { get; set; } = DistanceSpec.FromAtr(0.25);

        /// <summary>
        /// Reject sessions whose range is wider than this. A zero pip count or zero ATR multiple
        /// disables the check. A very wide range means the opposite-side stop is far away, so the
        /// sized position becomes tiny and the trade is mostly noise.
        /// </summary>
        public DistanceSpec MaxRange { get; set; } = DistanceSpec.FromAtr(0.0);

        /// <summary>
        /// Broker minimum distance between entry and stop, in pips. Orders violating it are
        /// rejected server-side, so we check before sending.
        /// </summary>
        public double MinStopDistancePips { get; set; } = 0.0;
    }

    /// <summary>
    /// Converts an <see cref="OpeningRange"/> into a concrete straddle. Pure: no cTrader types,
    /// no account state, no side effects. Everything here is exercised by unit tests.
    /// </summary>
    public sealed class BreakoutPlanner
    {
        private readonly BreakoutPlannerSettings _settings;

        public BreakoutPlanner(BreakoutPlannerSettings settings)
        {
            _settings = settings ?? throw new ArgumentNullException(nameof(settings));

            if (_settings.TargetRMultiple <= 0)
                throw new ArgumentException("Target R multiple must be positive.", nameof(settings));
            if (_settings.EntryBuffer == null)
                throw new ArgumentException("EntryBuffer must be set.", nameof(settings));
            if (_settings.MinRange == null)
                throw new ArgumentException("MinRange must be set.", nameof(settings));
            if (_settings.MaxRange == null)
                throw new ArgumentException("MaxRange must be set.", nameof(settings));
        }

        /// <param name="range">The pre-session range.</param>
        /// <param name="pipSize">
        /// The symbol's own pip size -- 0.01 on GBPJPY (3-digit quote), 0.0001 on GBPUSD
        /// (5-digit quote). Never assumed; the bot passes <c>Symbol.PipSize</c> straight through.
        /// </param>
        /// <param name="atrInPrice">
        /// The reference ATR in price units, on the symbol being traded. Consulted by every
        /// setting configured as an ATR multiple -- the entry buffer and range floor/ceiling by
        /// default, plus the stop when <see cref="StopMode.AtrMultiple"/> is selected. Pass 0
        /// when unavailable; sessions needing it are then skipped rather than silently falling
        /// back to a pip value that would be mis-scaled on one of the two symbols.
        /// </param>
        public BreakoutPlan BuildPlan(OpeningRange range, double pipSize, double atrInPrice = 0.0)
        {
            if (range == null) throw new ArgumentNullException(nameof(range));
            if (pipSize <= 0) throw new ArgumentOutOfRangeException(nameof(pipSize), pipSize, "Pip size must be positive.");

            var rangePips = range.HeightInPips(pipSize);

            var minRange = _settings.MinRange.ResolveToPrice(pipSize, atrInPrice, "Min range", out var minReason);
            if (minReason != null) return BreakoutPlan.Rejected(minReason);

            if (range.Height < minRange)
            {
                return BreakoutPlan.Rejected(
                    $"Range {rangePips:F1} pips is below the minimum of {minRange / pipSize:F1} pips " +
                    $"({_settings.MinRange}). A stop this tight would size the position dangerously large.");
            }

            var maxRange = _settings.MaxRange.ResolveToPrice(pipSize, atrInPrice, "Max range", out var maxReason);
            if (maxReason != null) return BreakoutPlan.Rejected(maxReason);

            if (maxRange > 0 && range.Height > maxRange)
            {
                return BreakoutPlan.Rejected(
                    $"Range {rangePips:F1} pips exceeds the maximum of {maxRange / pipSize:F1} pips " +
                    $"({_settings.MaxRange}).");
            }

            var buffer = _settings.EntryBuffer.ResolveToPrice(pipSize, atrInPrice, "Entry buffer", out var bufferReason);
            if (bufferReason != null) return BreakoutPlan.Rejected(bufferReason);

            var buyEntry = range.High + buffer;
            var sellEntry = range.Low - buffer;

            var stopDistance = ResolveStopDistance(range, pipSize, atrInPrice, buyEntry, sellEntry, out var reason);
            if (reason != null) return BreakoutPlan.Rejected(reason);

            var stopPips = stopDistance / pipSize;
            if (_settings.MinStopDistancePips > 0 && stopPips < _settings.MinStopDistancePips)
            {
                return BreakoutPlan.Rejected(
                    $"Stop distance {stopPips:F1} pips is below the broker minimum " +
                    $"({_settings.MinStopDistancePips:F1} pips).");
            }

            var targetDistance = stopDistance * _settings.TargetRMultiple;

            var buyLeg = new BreakoutLeg(
                isBuy: true,
                entryPrice: buyEntry,
                stopLossPrice: buyEntry - stopDistance,
                takeProfitPrice: buyEntry + targetDistance);

            var sellLeg = new BreakoutLeg(
                isBuy: false,
                entryPrice: sellEntry,
                stopLossPrice: sellEntry + stopDistance,
                takeProfitPrice: sellEntry - targetDistance);

            return BreakoutPlan.Straddle(buyLeg, sellLeg);
        }

        /// <summary>
        /// Both legs deliberately use the SAME stop distance. With the default
        /// <see cref="StopMode.OppositeRangeSide"/> that distance is the range height plus one
        /// buffer, measured from each entry to the far edge of the range. Keeping the legs
        /// symmetric means the risk per trade is identical whichever way price breaks, which is
        /// what makes a single RiskPercent figure meaningful.
        /// </summary>
        private double ResolveStopDistance(
            OpeningRange range,
            double pipSize,
            double atrInPrice,
            double buyEntry,
            double sellEntry,
            out string rejectionReason)
        {
            rejectionReason = null;

            switch (_settings.StopMode)
            {
                case StopMode.OppositeRangeSide:
                    // Long entered above the high is stopped at the low: distance = entry - low.
                    // Short entered below the low is stopped at the high: distance = high - entry.
                    // The buffer makes both identical: range height + buffer.
                    return buyEntry - range.Low;

                case StopMode.FixedPips:
                    if (_settings.FixedStopPips <= 0)
                    {
                        rejectionReason = "FixedStopPips must be positive when StopMode is FixedPips.";
                        return 0;
                    }
                    return _settings.FixedStopPips * pipSize;

                case StopMode.AtrMultiple:
                    if (atrInPrice <= 0)
                    {
                        rejectionReason = "ATR is not available yet (needs more history); skipping this session.";
                        return 0;
                    }
                    if (_settings.AtrMultiplier <= 0)
                    {
                        rejectionReason = "AtrMultiplier must be positive when StopMode is AtrMultiple.";
                        return 0;
                    }
                    return atrInPrice * _settings.AtrMultiplier;

                default:
                    rejectionReason = $"Unknown StopMode '{_settings.StopMode}'.";
                    return 0;
            }
        }
    }
}
