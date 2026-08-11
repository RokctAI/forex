using System;

namespace LondonBreakout.Core.Risk
{
    public sealed class SizingRequest
    {
        public SizingRequest(
            double equity,
            double riskPercent,
            double stopDistanceInPrice,
            SymbolConstraints constraints)
        {
            Equity = equity;
            RiskPercent = riskPercent;
            StopDistanceInPrice = stopDistanceInPrice;
            Constraints = constraints ?? throw new ArgumentNullException(nameof(constraints));
        }

        /// <summary>Account equity in the deposit currency.</summary>
        public double Equity { get; }

        /// <summary>Fraction of equity to put at risk, as a percentage (1.0 means 1%).</summary>
        public double RiskPercent { get; }

        /// <summary>Distance from entry to stop, in price units (not pips).</summary>
        public double StopDistanceInPrice { get; }

        public SymbolConstraints Constraints { get; }

        /// <summary>
        /// How much the clamped volume may overshoot the requested risk before the trade is
        /// refused outright, as a fraction. 0.10 means "reject if the smallest tradable size
        /// risks more than 110% of what was asked for".
        /// </summary>
        public double OverRiskTolerance { get; set; } = 0.10;
    }

    public sealed class SizingResult
    {
        private SizingResult(
            bool accepted,
            double volumeInUnits,
            double requestedRiskAmount,
            double actualRiskAmount,
            string reason)
        {
            Accepted = accepted;
            VolumeInUnits = volumeInUnits;
            RequestedRiskAmount = requestedRiskAmount;
            ActualRiskAmount = actualRiskAmount;
            Reason = reason;
        }

        public bool Accepted { get; }
        public double VolumeInUnits { get; }

        /// <summary>Equity * RiskPercent/100 -- what the user asked to risk.</summary>
        public double RequestedRiskAmount { get; }

        /// <summary>What will actually be at risk once the volume is on the broker's lot grid.</summary>
        public double ActualRiskAmount { get; }

        /// <summary>Explanation, always populated for rejections and for clamped acceptances.</summary>
        public string Reason { get; }

        public static SizingResult Accept(double volume, double requested, double actual, string reason = null)
            => new SizingResult(true, volume, requested, actual, reason);

        public static SizingResult Reject(string reason, double requested = 0, double actual = 0)
            => new SizingResult(false, 0, requested, actual, reason);

        public override string ToString()
            => Accepted
                ? $"ACCEPT {VolumeInUnits} units, risking {ActualRiskAmount:F2} of {RequestedRiskAmount:F2} requested"
                : $"REJECT: {Reason}";
    }

    /// <summary>
    /// Fixed-fractional position sizing.
    ///
    /// The rule: never risk more than RiskPercent of equity on one trade. Everything else --
    /// lot grids, broker minimums, tiny stops -- is handled as a constraint on that rule, and
    /// when the constraints make the rule impossible to honour the trade is refused rather than
    /// quietly enlarged.
    ///
    /// Pure and cTrader-free.
    /// </summary>
    public sealed class PositionSizer
    {
        public SizingResult Calculate(SizingRequest request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));

            var c = request.Constraints;

            if (request.Equity <= 0)
                return SizingResult.Reject($"Equity is {request.Equity:F2}; refusing to size a trade.");

            if (request.RiskPercent <= 0)
                return SizingResult.Reject($"RiskPercent is {request.RiskPercent}; must be positive.");

            if (request.StopDistanceInPrice <= 0)
                return SizingResult.Reject($"Stop distance is {request.StopDistanceInPrice}; must be positive.");

            var requestedRisk = request.Equity * (request.RiskPercent / 100.0);

            // Risk per unit of volume, in account currency.
            //
            // Note on units: PipValuePerUnit is denominated per PIP, so the stop distance has to
            // be converted from price into pips before the two are multiplied. Multiplying a raw
            // price distance by a per-pip value would be off by a factor of PipSize -- 10,000x on
            // a 5-digit FX pair, which would size every position catastrophically wrong. The
            // conversion is done explicitly here for that reason.
            var stopInPips = request.StopDistanceInPrice / c.PipSize;
            var riskPerUnit = stopInPips * c.PipValuePerUnit;

            if (riskPerUnit <= 0)
                return SizingResult.Reject("Computed risk-per-unit is not positive; check symbol pip data.");

            var rawVolume = requestedRisk / riskPerUnit;

            if (rawVolume > c.VolumeInUnitsMax)
            {
                // Capping at max reduces risk, which is always safe -- accept but say so.
                var cappedRisk = c.VolumeInUnitsMax * riskPerUnit;
                return SizingResult.Accept(
                    c.VolumeInUnitsMax,
                    requestedRisk,
                    cappedRisk,
                    $"Volume capped at symbol maximum ({c.VolumeInUnitsMax}); " +
                    $"risking {cappedRisk:F2} instead of the requested {requestedRisk:F2}.");
            }

            var volume = c.RoundDownToStep(rawVolume);

            if (volume < c.VolumeInUnitsMin)
                volume = c.VolumeInUnitsMin;

            var actualRisk = volume * riskPerUnit;

            // The dangerous direction: the smallest size the broker will accept risks MORE than
            // the user authorised. This happens on tight stops and small accounts. Refuse.
            var ceiling = requestedRisk * (1.0 + Math.Max(0.0, request.OverRiskTolerance));
            if (actualRisk > ceiling)
            {
                return SizingResult.Reject(
                    $"Smallest tradable size ({volume} units) would risk {actualRisk:F2}, " +
                    $"more than the {ceiling:F2} ceiling implied by RiskPercent={request.RiskPercent} " +
                    $"(+{request.OverRiskTolerance:P0} tolerance). Stop distance {stopInPips:F1} pips " +
                    "is too tight for this account size.",
                    requestedRisk,
                    actualRisk);
            }

            return SizingResult.Accept(volume, requestedRisk, actualRisk);
        }
    }
}
