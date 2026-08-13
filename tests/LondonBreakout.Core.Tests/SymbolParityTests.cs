using System;
using LondonBreakout.Core.Planning;
using LondonBreakout.Core.Ranges;
using LondonBreakout.Core.Risk;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    /// <summary>
    /// GBPJPY (primary) and GBPUSD (secondary) are NOT interchangeable, and these tests exist to
    /// keep that fact enforced rather than remembered.
    ///
    /// Two separate differences are at work, and conflating them is how this goes wrong:
    ///
    ///  1. QUOTE PRECISION -- a units problem. GBPJPY is quoted to 3 decimals so one pip is 0.01;
    ///     GBPUSD to 5 decimals so one pip is 0.0001. Every conversion between price distance and
    ///     pips must read the symbol's own pip size. Hardcoding 0.0001 is wrong by 100x on
    ///     GBPJPY, and the resulting position size still looks like a plausible number.
    ///
    ///  2. TYPICAL RANGE -- not a units problem, and not fixable by arithmetic. GBPJPY's daily
    ///     range is roughly double GBPUSD's, so the same pip count is a materially tighter
    ///     distance on GBPJPY in the only sense that matters: how likely price is to travel it.
    ///     This is why the pip-denominated defaults were made volatility-relative.
    ///
    /// Numbers below are representative rather than measured: no market data has been through
    /// this bot. They are internally consistent, which is all these tests need.
    /// </summary>
    public class SymbolParityTests
    {
        // ------------------------------------------------------------------ Symbol definitions

        private const double GbpJpyPip = 0.01;      // 3-digit quote
        private const double GbpUsdPip = 0.0001;    // 5-digit quote

        /// <summary>Representative daily ATR: ~120 pips on GBPJPY.</summary>
        private const double GbpJpyAtr = 1.20;

        /// <summary>Representative daily ATR: ~70 pips on GBPUSD. Roughly half, in pip terms.</summary>
        private const double GbpUsdAtr = 0.0070;

        /// <summary>
        /// GBPJPY sized from a USD account. A pip on one unit is 0.01 JPY, which at ~157 JPY/USD
        /// is ~0.0000637 USD. That conversion is what cTrader's Symbol.PipValue already does;
        /// see SymbolConstraints for why it must never be hand-rolled.
        /// </summary>
        private static SymbolConstraints GbpJpy(double min = 1, double step = 1, double max = 100_000_000)
            => new SymbolConstraints(min, max, step, pipSize: GbpJpyPip, pipValuePerUnit: 0.0000637);

        /// <summary>GBPUSD from a USD account: a pip on one unit is 0.0001 USD directly.</summary>
        private static SymbolConstraints GbpUsd(double min = 1, double step = 1, double max = 100_000_000)
            => new SymbolConstraints(min, max, step, pipSize: GbpUsdPip, pipValuePerUnit: 0.0001);

        private static OpeningRange RangeOf(double low, double high)
            => new OpeningRange(high, low, 100,
                new DateTime(2026, 7, 13, 23, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 7, 14, 8, 0, 0, DateTimeKind.Utc));

        /// <summary>A GBPJPY range of the given pip width, centred near 195.000.</summary>
        private static OpeningRange JpyRange(double pips)
            => RangeOf(195.000 - (pips / 2 * GbpJpyPip), 195.000 + (pips / 2 * GbpJpyPip));

        /// <summary>A GBPUSD range of the given pip width, centred near 1.27000.</summary>
        private static OpeningRange UsdRange(double pips)
            => RangeOf(1.27000 - (pips / 2 * GbpUsdPip), 1.27000 + (pips / 2 * GbpUsdPip));

        // ------------------------------------------------------- Pip size is read, not assumed

        [Fact]
        public void Range_height_in_pips_is_correct_on_both_quote_precisions()
        {
            // Same 50 pips, two completely different price distances.
            Assert.Equal(50.0, JpyRange(50).HeightInPips(GbpJpyPip), 4);
            Assert.Equal(0.50, JpyRange(50).Height, 6);

            Assert.Equal(50.0, UsdRange(50).HeightInPips(GbpUsdPip), 4);
            Assert.Equal(0.0050, UsdRange(50).Height, 8);
        }

        [Fact]
        public void Assuming_five_digits_on_a_jpy_pair_sizes_the_position_100x_wrong()
        {
            // This is the regression this whole file guards. The ONLY difference between the two
            // calls is the pip size handed to the sizer; the stop distance in price is identical
            // and correct in both. Reading it from the symbol gives the right answer; assuming a
            // 5-digit pip gives a position 100x too small -- and on the other side of a similar
            // mistake, 100x too large.
            var sizer = new PositionSizer();
            const double fiftyPipsOnGbpJpy = 0.50;

            var correct = sizer.Calculate(
                new SizingRequest(10_000, 1.0, fiftyPipsOnGbpJpy, GbpJpy()));

            var assumesFiveDigits = sizer.Calculate(
                new SizingRequest(10_000, 1.0, fiftyPipsOnGbpJpy,
                    new SymbolConstraints(1, 100_000_000, 1, pipSize: 0.0001, pipValuePerUnit: 0.0000637)));

            Assert.True(correct.Accepted, correct.Reason);
            Assert.True(assumesFiveDigits.Accepted, assumesFiveDigits.Reason);

            // Two orders of magnitude apart. Not exactly 100.0 only because each side is rounded
            // down onto the whole-unit lot grid independently.
            Assert.InRange(correct.VolumeInUnits / assumesFiveDigits.VolumeInUnits, 99.0, 101.0);
        }

        [Fact]
        public void Sizes_gbpjpy_and_gbpusd_to_the_same_risk_from_their_own_pip_data()
        {
            // A 50 pip stop on a $10,000 account at 1% risk. The price distances differ by 100x
            // and the pip values differ too, but both must land on the SAME risk in dollars.
            var sizer = new PositionSizer();

            var jpy = sizer.Calculate(new SizingRequest(10_000, 1.0, 50 * GbpJpyPip, GbpJpy()));
            var usd = sizer.Calculate(new SizingRequest(10_000, 1.0, 50 * GbpUsdPip, GbpUsd()));

            Assert.True(jpy.Accepted, jpy.Reason);
            Assert.True(usd.Accepted, usd.Reason);

            // Both risk the requested $100 (to within one unit of the lot grid).
            Assert.Equal(100.0, jpy.ActualRiskAmount, 1);
            Assert.Equal(100.0, usd.ActualRiskAmount, 1);
            Assert.True(jpy.ActualRiskAmount <= 100.0);
            Assert.True(usd.ActualRiskAmount <= 100.0);

            // The VOLUMES differ, and should: a JPY pip is worth far less per unit in USD, so a
            // dollar-equal risk needs a bigger position. Equal volumes would be the bug.
            Assert.Equal(20_000, usd.VolumeInUnits, 6);
            Assert.True(jpy.VolumeInUnits > usd.VolumeInUnits);
        }

        [Theory]
        // stop pips, then the price distance that means on each symbol
        [InlineData(10)]
        [InlineData(35)]
        [InlineData(120)]
        public void Halving_the_stop_doubles_the_size_on_both_symbols(double stopPips)
        {
            var sizer = new PositionSizer();

            foreach (var (pip, constraints) in new[]
                     {
                         (GbpJpyPip, GbpJpy()),
                         (GbpUsdPip, GbpUsd()),
                     })
            {
                var wide = sizer.Calculate(new SizingRequest(100_000, 1.0, stopPips * pip, constraints));
                var tight = sizer.Calculate(new SizingRequest(100_000, 1.0, stopPips / 2 * pip, constraints));

                Assert.True(wide.Accepted, wide.Reason);
                Assert.True(tight.Accepted, tight.Reason);

                // Within rounding of exactly double, on both quote precisions.
                Assert.InRange(tight.VolumeInUnits / wide.VolumeInUnits, 1.999, 2.001);
            }
        }

        [Fact]
        public void Broker_minimum_lot_over_risk_is_caught_on_a_jpy_pair_too()
        {
            // The over-risk refusal must not be a 5-digit-only safeguard. A tiny account on a
            // 1,000-unit minimum lot with a 10 pip GBPJPY stop.
            var result = new PositionSizer().Calculate(
                new SizingRequest(50, 1.0, 10 * GbpJpyPip, GbpJpy(min: 1000, step: 1000)));

            Assert.False(result.Accepted);
            Assert.Contains("more than", result.Reason);
        }

        // ------------------------------------------------- Volatility-relative vs fixed pips

        [Fact]
        public void A_fixed_pip_buffer_is_a_different_fraction_of_ATR_on_each_symbol()
        {
            // Documents the hazard the ATR default exists to remove. One pip is 1/120th of a
            // day's range on GBPJPY and 1/70th on GBPUSD -- the same parameter, nearly double
            // the effect. This test asserts the problem is real, not that the code is wrong.
            var oneJpyPipAsAtrFraction = GbpJpyPip / GbpJpyAtr;   // ~0.0083
            var oneUsdPipAsAtrFraction = GbpUsdPip / GbpUsdAtr;   // ~0.0143

            Assert.True(oneUsdPipAsAtrFraction > oneJpyPipAsAtrFraction * 1.5);
        }

        [Fact]
        public void An_ATR_buffer_puts_the_entry_the_same_distance_out_in_volatility_terms()
        {
            var settings = AtrSettings();

            var jpy = new BreakoutPlanner(settings).BuildPlan(JpyRange(50), GbpJpyPip, GbpJpyAtr);
            var usd = new BreakoutPlanner(settings).BuildPlan(UsdRange(50), GbpUsdPip, GbpUsdAtr);

            Assert.True(jpy.HasLegs);
            Assert.True(usd.HasLegs);

            // 0.05 x ATR: 6 pips on GBPJPY, 3.5 pips on GBPUSD. Different pip counts on purpose.
            var jpyBufferPips = (jpy.BuyLeg.EntryPrice - JpyRange(50).High) / GbpJpyPip;
            var usdBufferPips = (usd.BuyLeg.EntryPrice - UsdRange(50).High) / GbpUsdPip;

            Assert.Equal(6.0, jpyBufferPips, 3);
            Assert.Equal(3.5, usdBufferPips, 3);

            // But identical as a fraction of each symbol's own ATR -- which is the point.
            Assert.Equal(
                jpyBufferPips * GbpJpyPip / GbpJpyAtr,
                usdBufferPips * GbpUsdPip / GbpUsdAtr,
                6);
        }

        [Fact]
        public void An_ATR_range_floor_filters_a_quiet_jpy_session_that_a_shared_pip_floor_lets_through()
        {
            // A 25 pip range is QUIET on GBPJPY (0.21 x ATR) and NORMAL on GBPUSD (0.36 x ATR).
            // A shared 20-pip floor accepts both; the 0.25 x ATR floor correctly separates them.
            var pipFloor = FixedSettings();
            pipFloor.MinRange = DistanceSpec.FromPips(20.0);

            Assert.True(new BreakoutPlanner(pipFloor).BuildPlan(JpyRange(25), GbpJpyPip, GbpJpyAtr).HasLegs);
            Assert.True(new BreakoutPlanner(pipFloor).BuildPlan(UsdRange(25), GbpUsdPip, GbpUsdAtr).HasLegs);

            var atrFloor = AtrSettings();   // MinRange = 0.25 x ATR

            var jpy = new BreakoutPlanner(atrFloor).BuildPlan(JpyRange(25), GbpJpyPip, GbpJpyAtr);
            var usd = new BreakoutPlanner(atrFloor).BuildPlan(UsdRange(25), GbpUsdPip, GbpUsdAtr);

            Assert.False(jpy.HasLegs);
            Assert.Contains("below the minimum", jpy.RejectionReason);
            Assert.True(usd.HasLegs);
        }

        [Fact]
        public void The_ATR_range_floor_accepts_a_normal_session_on_both_symbols()
        {
            var settings = AtrSettings();

            // ~40% of a day's range overnight is an ordinary session on either symbol.
            Assert.True(new BreakoutPlanner(settings).BuildPlan(JpyRange(48), GbpJpyPip, GbpJpyAtr).HasLegs);
            Assert.True(new BreakoutPlanner(settings).BuildPlan(UsdRange(28), GbpUsdPip, GbpUsdAtr).HasLegs);
        }

        [Fact]
        public void Stop_distances_stay_symmetric_and_correctly_scaled_on_a_jpy_pair()
        {
            // The opposite-side stop on a 50 pip GBPJPY range with a 6 pip ATR buffer is 56 pips,
            // which is 0.56 in price. Both legs identical, so one sizing call covers both.
            var plan = new BreakoutPlanner(AtrSettings()).BuildPlan(JpyRange(50), GbpJpyPip, GbpJpyAtr);

            Assert.Equal(plan.BuyLeg.StopDistance, plan.SellLeg.StopDistance, 9);
            Assert.Equal(56.0, plan.BuyLeg.StopDistanceInPips(GbpJpyPip), 3);
            Assert.Equal(0.56, plan.BuyLeg.StopDistance, 6);

            // And that stop distance feeds the sizer as a price, which re-derives the pips from
            // the symbol's own pip size. End to end on the primary symbol.
            var sizing = new PositionSizer().Calculate(
                new SizingRequest(10_000, 0.5, plan.BuyLeg.StopDistance, GbpJpy()));

            Assert.True(sizing.Accepted, sizing.Reason);
            Assert.True(sizing.ActualRiskAmount <= 50.0);
            Assert.Equal(50.0, sizing.ActualRiskAmount, 0);
        }

        // -------------------------------------------------------------- ATR availability rules

        [Fact]
        public void ATR_relative_settings_skip_the_session_rather_than_guessing_when_ATR_is_missing()
        {
            // A silent fallback to a pip default is exactly how a value tuned for one symbol
            // ends up applied to the other. Skipping is the safe failure.
            var plan = new BreakoutPlanner(AtrSettings()).BuildPlan(JpyRange(50), GbpJpyPip, atrInPrice: 0.0);

            Assert.False(plan.HasLegs);
            Assert.Contains("ATR", plan.RejectionReason);
        }

        [Fact]
        public void Fixed_pip_mode_still_works_and_needs_no_ATR()
        {
            var settings = FixedSettings();

            var plan = new BreakoutPlanner(settings).BuildPlan(JpyRange(50), GbpJpyPip, atrInPrice: 0.0);

            Assert.True(plan.HasLegs);
            Assert.Equal(1.0, (plan.BuyLeg.EntryPrice - JpyRange(50).High) / GbpJpyPip, 3);
        }

        // ------------------------------------------------------------------------- Fixtures

        /// <summary>The shipped defaults: everything volatility-relative.</summary>
        private static BreakoutPlannerSettings AtrSettings() => new BreakoutPlannerSettings
        {
            EntryBuffer = DistanceSpec.FromAtr(0.05),
            MinRange = DistanceSpec.FromAtr(0.25),
            MaxRange = DistanceSpec.FromAtr(0.0),
            StopMode = StopMode.OppositeRangeSide,
            TargetRMultiple = 1.0,
        };

        /// <summary>The fixed-pip alternative, which remains available.</summary>
        private static BreakoutPlannerSettings FixedSettings() => new BreakoutPlannerSettings
        {
            EntryBuffer = DistanceSpec.FromPips(1.0),
            MinRange = DistanceSpec.FromPips(5.0),
            MaxRange = DistanceSpec.FromPips(0.0),
            StopMode = StopMode.OppositeRangeSide,
            TargetRMultiple = 1.0,
        };
    }
}
