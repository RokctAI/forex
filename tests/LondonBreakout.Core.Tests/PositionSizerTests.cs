using LondonBreakout.Core.Risk;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    /// <summary>
    /// Sizing is the other place where a silent bug is expensive: the bot keeps trading, it just
    /// trades far too big. These tests pin the arithmetic to worked examples.
    /// </summary>
    public class PositionSizerTests
    {
        /// <summary>
        /// EURUSD on a USD account: pip size 0.0001, and one pip on one unit is worth $0.0001
        /// (so a 100,000-unit lot moves $10 per pip). Broker lot grid: 1k min, 1k steps.
        /// </summary>
        private static SymbolConstraints EurUsd(
            double min = 1000, double max = 100_000_000, double step = 1000)
            => new SymbolConstraints(min, max, step, pipSize: 0.0001, pipValuePerUnit: 0.0001);

        [Fact]
        public void Sizes_a_textbook_trade_exactly()
        {
            // $10,000 equity, 1% risk = $100. A 20 pip stop is $0.002 of risk per unit,
            // so $100 / 0.002 = 50,000 units.
            var result = new PositionSizer().Calculate(
                new SizingRequest(equity: 10_000, riskPercent: 1.0, stopDistanceInPrice: 0.0020, EurUsd()));

            Assert.True(result.Accepted, result.Reason);
            Assert.Equal(50_000, result.VolumeInUnits, 6);
            Assert.Equal(100.0, result.RequestedRiskAmount, 6);
            Assert.Equal(100.0, result.ActualRiskAmount, 6);
        }

        [Fact]
        public void Stop_distance_is_converted_from_price_to_pips_before_sizing()
        {
            // The unit trap. If a raw price distance (0.0020) were multiplied by a per-pip value
            // (0.0001) the denominator would be 10,000x too small and the position 10,000x too
            // large. Halving the stop must exactly double the size -- and the absolute numbers
            // must stay sane.
            var sizer = new PositionSizer();

            var wide = sizer.Calculate(
                new SizingRequest(10_000, 1.0, 0.0020, EurUsd()));
            var tight = sizer.Calculate(
                new SizingRequest(10_000, 1.0, 0.0010, EurUsd()));

            Assert.Equal(50_000, wide.VolumeInUnits, 6);
            Assert.Equal(100_000, tight.VolumeInUnits, 6);
            Assert.Equal(wide.VolumeInUnits * 2, tight.VolumeInUnits, 6);
        }

        [Fact]
        public void Risk_scales_linearly_with_equity_and_with_risk_percent()
        {
            var sizer = new PositionSizer();

            var baseline = sizer.Calculate(new SizingRequest(10_000, 1.0, 0.0020, EurUsd()));
            var doubleEquity = sizer.Calculate(new SizingRequest(20_000, 1.0, 0.0020, EurUsd()));
            var doubleRisk = sizer.Calculate(new SizingRequest(10_000, 2.0, 0.0020, EurUsd()));

            Assert.Equal(baseline.VolumeInUnits * 2, doubleEquity.VolumeInUnits, 6);
            Assert.Equal(baseline.VolumeInUnits * 2, doubleRisk.VolumeInUnits, 6);
        }

        [Fact]
        public void Volume_is_rounded_down_onto_the_lot_grid_never_up()
        {
            // Raw size lands at 50,500 units; the grid only allows multiples of 1,000.
            // Rounding up would push realised risk above the requested percentage.
            var result = new PositionSizer().Calculate(
                new SizingRequest(10_100, 1.0, 0.0020, EurUsd()));

            Assert.True(result.Accepted, result.Reason);
            Assert.Equal(50_000, result.VolumeInUnits, 6);
            Assert.True(result.ActualRiskAmount <= result.RequestedRiskAmount);
        }

        [Fact]
        public void Refuses_when_the_broker_minimum_lot_would_over_risk_the_account()
        {
            // $200 account, 1% risk = $2. A 20 pip stop on the 10,000-unit minimum risks $20:
            // ten times the authorised amount. Taking it anyway is exactly the behaviour this
            // layer exists to prevent.
            var result = new PositionSizer().Calculate(
                new SizingRequest(200, 1.0, 0.0020, EurUsd(min: 10_000, step: 10_000)));

            Assert.False(result.Accepted);
            Assert.Contains("more than", result.Reason);
            Assert.Equal(0, result.VolumeInUnits);
        }

        [Fact]
        public void Accepts_a_small_overshoot_inside_the_tolerance()
        {
            // Minimum lot risks $20; requested risk $19 with a 10% tolerance allows up to $20.90.
            var request = new SizingRequest(1900, 1.0, 0.0020, EurUsd(min: 10_000, step: 10_000))
            {
                OverRiskTolerance = 0.10,
            };

            var result = new PositionSizer().Calculate(request);

            Assert.True(result.Accepted, result.Reason);
            Assert.Equal(10_000, result.VolumeInUnits, 6);
            Assert.Equal(20.0, result.ActualRiskAmount, 6);
        }

        [Fact]
        public void Zero_tolerance_refuses_any_overshoot()
        {
            var request = new SizingRequest(1900, 1.0, 0.0020, EurUsd(min: 10_000, step: 10_000))
            {
                OverRiskTolerance = 0.0,
            };

            Assert.False(new PositionSizer().Calculate(request).Accepted);
        }

        [Fact]
        public void Caps_at_the_symbol_maximum_and_says_so()
        {
            // Capping reduces risk, so it is safe to accept -- but the user should be told the
            // trade is smaller than their risk setting implies.
            var result = new PositionSizer().Calculate(
                new SizingRequest(10_000_000, 5.0, 0.0020, EurUsd(max: 100_000)));

            Assert.True(result.Accepted);
            Assert.Equal(100_000, result.VolumeInUnits, 6);
            Assert.True(result.ActualRiskAmount < result.RequestedRiskAmount);
            Assert.Contains("capped", result.Reason);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(-500)]
        public void Refuses_non_positive_equity(double equity)
        {
            var result = new PositionSizer().Calculate(new SizingRequest(equity, 1.0, 0.0020, EurUsd()));

            Assert.False(result.Accepted);
            Assert.Contains("Equity", result.Reason);
        }

        [Fact]
        public void Refuses_a_non_positive_stop_distance()
        {
            var result = new PositionSizer().Calculate(new SizingRequest(10_000, 1.0, 0.0, EurUsd()));

            Assert.False(result.Accepted);
            Assert.Contains("Stop distance", result.Reason);
        }

        [Fact]
        public void Refuses_a_non_positive_risk_percent()
        {
            var result = new PositionSizer().Calculate(new SizingRequest(10_000, 0.0, 0.0020, EurUsd()));

            Assert.False(result.Accepted);
            Assert.Contains("RiskPercent", result.Reason);
        }

        [Fact]
        public void Works_for_a_jpy_pair_where_pip_size_is_two_decimals()
        {
            // USDJPY: pip size 0.01. A 20 pip stop is 0.20 in price terms. With a per-unit pip
            // value of 0.0067 USD, risk per unit is 20 * 0.0067 = 0.134, so $100 of risk buys
            // 746.26 units, which rounds down to 746 on a 1-unit grid.
            var usdJpy = new SymbolConstraints(1, 100_000_000, 1, pipSize: 0.01, pipValuePerUnit: 0.0067);

            var result = new PositionSizer().Calculate(
                new SizingRequest(10_000, 1.0, 0.20, usdJpy));

            Assert.True(result.Accepted, result.Reason);
            Assert.Equal(746, result.VolumeInUnits, 6);
            Assert.True(result.ActualRiskAmount <= 100.0);
        }

        [Fact]
        public void RoundDownToStep_lands_exactly_on_grid_multiples()
        {
            var c = EurUsd();

            Assert.Equal(1000, c.RoundDownToStep(1000), 6);
            Assert.Equal(1000, c.RoundDownToStep(1999), 6);
            Assert.Equal(2000, c.RoundDownToStep(2000), 6);
            Assert.Equal(51_000, c.RoundDownToStep(51_000), 6);
            Assert.Equal(1000, c.RoundDownToStep(500), 6);   // below min clamps up to min
        }
    }
}
