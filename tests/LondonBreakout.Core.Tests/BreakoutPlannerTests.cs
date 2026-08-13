using System;
using LondonBreakout.Core.Planning;
using LondonBreakout.Core.Ranges;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    public class BreakoutPlannerTests
    {
        private const double PipSize = 0.0001;

        private static OpeningRange Range(double low = 1.0950, double high = 1.1000)
            => new OpeningRange(high, low, 100,
                new DateTime(2026, 7, 14, 23, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc));

        private static BreakoutPlannerSettings Settings() => new BreakoutPlannerSettings
        {
            EntryBuffer = DistanceSpec.FromPips(1.0),
            StopMode = StopMode.OppositeRangeSide,
            TargetRMultiple = 1.0,
            MinRange = DistanceSpec.FromPips(5.0),
            MaxRange = DistanceSpec.FromPips(0.0),
        };

        [Fact]
        public void Entries_sit_one_buffer_outside_each_range_edge()
        {
            var plan = new BreakoutPlanner(Settings()).BuildPlan(Range(), PipSize);

            Assert.True(plan.HasLegs);
            Assert.Equal(1.1001, plan.BuyLeg.EntryPrice, 6);   // high + 1 pip
            Assert.Equal(1.0949, plan.SellLeg.EntryPrice, 6);  // low  - 1 pip
        }

        [Fact]
        public void Nothing_is_placed_inside_the_range()
        {
            // "We don't trade inside those lines": both entries must be strictly outside.
            var range = Range();
            var plan = new BreakoutPlanner(Settings()).BuildPlan(range, PipSize);

            Assert.True(plan.BuyLeg.EntryPrice > range.High);
            Assert.True(plan.SellLeg.EntryPrice < range.Low);
        }

        [Fact]
        public void Opposite_side_stop_puts_each_stop_on_the_far_edge_of_the_range()
        {
            var plan = new BreakoutPlanner(Settings()).BuildPlan(Range(), PipSize);

            // Long entered above the high is stopped at the range low.
            Assert.Equal(1.0950, plan.BuyLeg.StopLossPrice, 6);
            // Short entered below the low is stopped at the range high.
            Assert.Equal(1.1000, plan.SellLeg.StopLossPrice, 6);
        }

        [Fact]
        public void Both_legs_carry_an_identical_stop_distance()
        {
            // This is what makes a single RiskPercent figure meaningful: the loss is the same
            // whichever way price breaks, so one sizing calculation covers both orders.
            var plan = new BreakoutPlanner(Settings()).BuildPlan(Range(), PipSize);

            Assert.Equal(plan.BuyLeg.StopDistance, plan.SellLeg.StopDistance, 9);
            Assert.Equal(51.0, plan.BuyLeg.StopDistanceInPips(PipSize), 4);  // 50 pip range + 1 buffer
        }

        [Theory]
        [InlineData(1.0, 51.0)]
        [InlineData(2.0, 102.0)]
        [InlineData(0.5, 25.5)]
        public void Target_distance_is_the_stop_distance_times_the_r_multiple(double r, double expectedPips)
        {
            var settings = Settings();
            settings.TargetRMultiple = r;

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize);

            Assert.Equal(expectedPips, plan.BuyLeg.TargetDistanceInPips(PipSize), 4);
            Assert.Equal(expectedPips, plan.SellLeg.TargetDistanceInPips(PipSize), 4);
        }

        [Fact]
        public void Targets_point_away_from_the_range_in_the_trade_direction()
        {
            var plan = new BreakoutPlanner(Settings()).BuildPlan(Range(), PipSize);

            Assert.True(plan.BuyLeg.TakeProfitPrice > plan.BuyLeg.EntryPrice);
            Assert.True(plan.SellLeg.TakeProfitPrice < plan.SellLeg.EntryPrice);
        }

        [Fact]
        public void Fixed_pip_stop_mode_ignores_range_geometry()
        {
            var settings = Settings();
            settings.StopMode = StopMode.FixedPips;
            settings.FixedStopPips = 15.0;

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize);

            Assert.Equal(15.0, plan.BuyLeg.StopDistanceInPips(PipSize), 4);
            Assert.Equal(15.0, plan.SellLeg.StopDistanceInPips(PipSize), 4);
        }

        [Fact]
        public void Atr_stop_mode_scales_with_the_atr_multiplier()
        {
            var settings = Settings();
            settings.StopMode = StopMode.AtrMultiple;
            settings.AtrMultiplier = 2.0;

            // ATR of 0.0010 (10 pips) x 2 = 20 pips.
            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize, atrInPrice: 0.0010);

            Assert.Equal(20.0, plan.BuyLeg.StopDistanceInPips(PipSize), 4);
        }

        [Fact]
        public void Atr_stop_mode_rejects_the_session_when_atr_is_not_ready()
        {
            var settings = Settings();
            settings.StopMode = StopMode.AtrMultiple;

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize, atrInPrice: 0.0);

            Assert.False(plan.HasLegs);
            Assert.Contains("ATR", plan.RejectionReason);
        }

        [Fact]
        public void A_range_narrower_than_the_minimum_is_rejected()
        {
            // A 2 pip range would produce a ~3 pip stop and therefore an enormous position.
            var settings = Settings();
            settings.MinRange = DistanceSpec.FromPips(5.0);

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(1.0998, 1.1000), PipSize);

            Assert.False(plan.HasLegs);
            Assert.Contains("below the minimum", plan.RejectionReason);
        }

        [Fact]
        public void A_range_wider_than_the_maximum_is_rejected_when_the_check_is_enabled()
        {
            var settings = Settings();
            settings.MaxRange = DistanceSpec.FromPips(40.0);

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize); // 50 pips

            Assert.False(plan.HasLegs);
            Assert.Contains("exceeds the maximum", plan.RejectionReason);
        }

        [Fact]
        public void Max_range_check_is_disabled_at_zero()
        {
            var settings = Settings();
            settings.MaxRange = DistanceSpec.FromPips(0.0);

            Assert.True(new BreakoutPlanner(settings).BuildPlan(Range(), PipSize).HasLegs);
        }

        [Fact]
        public void A_stop_below_the_broker_minimum_distance_is_rejected()
        {
            var settings = Settings();
            settings.StopMode = StopMode.FixedPips;
            settings.FixedStopPips = 2.0;
            settings.MinStopDistancePips = 10.0;

            var plan = new BreakoutPlanner(settings).BuildPlan(Range(), PipSize);

            Assert.False(plan.HasLegs);
            Assert.Contains("broker minimum", plan.RejectionReason);
        }

        [Fact]
        public void A_negative_r_multiple_is_rejected_at_construction()
        {
            var settings = Settings();
            settings.TargetRMultiple = -1.0;

            Assert.Throws<ArgumentException>(() => new BreakoutPlanner(settings));
        }

        [Fact]
        public void Leg_construction_rejects_a_stop_on_the_wrong_side_of_the_entry()
        {
            // Defensive: a long whose stop sits above its entry is a coding error, not a trade.
            Assert.Throws<ArgumentException>(
                () => new BreakoutLeg(isBuy: true, entryPrice: 1.10, stopLossPrice: 1.11, takeProfitPrice: 1.12));

            Assert.Throws<ArgumentException>(
                () => new BreakoutLeg(isBuy: false, entryPrice: 1.10, stopLossPrice: 1.09, takeProfitPrice: 1.08));
        }
    }
}
