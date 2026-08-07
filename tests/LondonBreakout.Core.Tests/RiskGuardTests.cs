using System;
using LondonBreakout.Core.Risk;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    public class RiskGuardTests
    {
        private static readonly DateTime Day1 = new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc);
        private static readonly DateTime Day2 = new DateTime(2026, 7, 16, 8, 0, 0, DateTimeKind.Utc);

        private static RiskLimits Limits() => new RiskLimits
        {
            RiskPercentPerTrade = 1.0,
            MaxDailyLossPercent = 2.0,
            MaxDrawdownPercent = 10.0,
            MaxConcurrentPositions = 1,
            MaxMarginUtilisationPercent = 20.0,
            TradingEnabled = true,
        };

        private static AccountSnapshot Snap(
            double equity, int positions = 0, double margin = 0, DateTime? at = null)
            => new AccountSnapshot(equity, equity, margin, positions, at ?? Day1);

        [Fact]
        public void Allows_a_normal_entry()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            Assert.True(guard.EvaluateEntry(Snap(10_000)).Allowed);
        }

        [Fact]
        public void Kill_switch_blocks_everything()
        {
            var limits = Limits();
            var guard = new RiskGuard(limits);
            guard.Initialise(10_000, Day1.Date);

            limits.TradingEnabled = false;

            var decision = guard.EvaluateEntry(Snap(10_000));

            Assert.False(decision.Allowed);
            Assert.Contains("Kill switch", decision.Reason);
        }

        [Fact]
        public void Kill_switch_can_be_flipped_back_on_without_a_restart()
        {
            var limits = Limits();
            var guard = new RiskGuard(limits);
            guard.Initialise(10_000, Day1.Date);

            limits.TradingEnabled = false;
            Assert.False(guard.EvaluateEntry(Snap(10_000)).Allowed);

            limits.TradingEnabled = true;
            Assert.True(guard.EvaluateEntry(Snap(10_000)).Allowed);
        }

        [Fact]
        public void Daily_loss_limit_blocks_new_entries_once_breached()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            // Down 2.5% on the day, limit is 2%.
            guard.Observe(Snap(9_750));

            var decision = guard.EvaluateEntry(Snap(9_750));

            Assert.True(guard.DailyLossBreached);
            Assert.False(decision.Allowed);
            Assert.Contains("Daily loss", decision.Reason);
        }

        [Fact]
        public void Daily_loss_breach_latches_even_if_equity_recovers_intraday()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(9_750));   // breach
            guard.Observe(Snap(9_990));   // recovers

            // Deliberate: the day's risk budget has been spent. Chasing it back is how a bad
            // day becomes a bad week.
            Assert.False(guard.EvaluateEntry(Snap(9_990)).Allowed);
        }

        [Fact]
        public void Daily_loss_resets_on_the_next_session()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(9_750));
            Assert.True(guard.DailyLossBreached);

            guard.OnSessionDate(Day2.Date, 9_750);

            Assert.False(guard.DailyLossBreached);
            Assert.Equal(9_750, guard.DayStartEquity);
            Assert.True(guard.EvaluateEntry(Snap(9_750, at: Day2)).Allowed);
        }

        [Fact]
        public void OnSessionDate_is_idempotent_within_a_session()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(9_900));
            guard.OnSessionDate(Day1.Date, 9_900);
            guard.OnSessionDate(Day1.Date, 9_800);

            // The baseline must not drift down as the day goes on, or the daily loss limit
            // would never trigger.
            Assert.Equal(10_000, guard.DayStartEquity);
        }

        [Fact]
        public void Drawdown_from_the_equity_peak_triggers_flatten_and_halt()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(12_000));            // new peak
            var decision = guard.Observe(Snap(10_700)); // 10.8% below the peak

            Assert.True(decision.RequiresFlatten);
            Assert.True(decision.RequiresHalt);
            Assert.True(guard.IsHalted);
            Assert.Contains("Max drawdown", decision.Reason);
        }

        [Fact]
        public void Drawdown_is_measured_from_the_peak_not_the_starting_balance()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(12_000));

            // 11,000 is above the starting balance but 8.3% below the peak: still inside the
            // 10% limit, so trading continues.
            Assert.False(guard.Observe(Snap(11_000)).RequiresHalt);
            Assert.Equal(12_000, guard.EquityPeak);

            // 10,000 is level with the start but 16.7% below the peak: halt.
            Assert.True(guard.Observe(Snap(10_000)).RequiresHalt);
        }

        [Fact]
        public void Halt_latches_and_blocks_all_later_entries()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(8_000));  // 20% drawdown
            Assert.True(guard.IsHalted);

            // Even a full recovery and a new session must not un-halt it: a human has to look.
            guard.OnSessionDate(Day2.Date, 15_000);
            var decision = guard.EvaluateEntry(Snap(15_000, at: Day2));

            Assert.False(decision.Allowed);
            Assert.True(guard.IsHalted);
        }

        [Fact]
        public void Max_concurrent_positions_blocks_a_second_entry()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            var decision = guard.EvaluateEntry(Snap(10_000, positions: 1), newPositionsWanted: 1);

            Assert.False(decision.Allowed);
            Assert.Contains("MaxConcurrentPositions", decision.Reason);
        }

        [Fact]
        public void Margin_utilisation_ceiling_blocks_an_entry()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            // 2,500 of margin on 10,000 equity is 25%, above the 20% ceiling.
            var decision = guard.EvaluateEntry(Snap(10_000, margin: 2_500));

            Assert.False(decision.Allowed);
            Assert.Contains("Margin utilisation", decision.Reason);
        }

        [Fact]
        public void Projected_margin_blocks_an_entry_that_would_cross_the_ceiling()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            // Currently 10% utilised; the new order would add another 15%.
            var decision = guard.EvaluateProjectedMargin(Snap(10_000, margin: 1_000), estimatedMargin: 1_500);

            Assert.False(decision.Allowed);
            Assert.Contains("Projected margin", decision.Reason);
        }

        [Fact]
        public void Projected_margin_allows_an_entry_that_stays_inside_the_ceiling()
        {
            var guard = new RiskGuard(Limits());
            guard.Initialise(10_000, Day1.Date);

            Assert.True(guard.EvaluateProjectedMargin(Snap(10_000, margin: 1_000), 500).Allowed);
        }

        [Fact]
        public void Zero_limits_disable_the_individual_checks()
        {
            var limits = new RiskLimits
            {
                MaxDailyLossPercent = 0,
                MaxDrawdownPercent = 0,
                MaxConcurrentPositions = 0,
                MaxMarginUtilisationPercent = 0,
                TradingEnabled = true,
            };
            var guard = new RiskGuard(limits);
            guard.Initialise(10_000, Day1.Date);

            guard.Observe(Snap(1_000));  // a 90% drawdown

            Assert.False(guard.IsHalted);
            Assert.True(guard.EvaluateEntry(Snap(1_000, positions: 50, margin: 900)).Allowed);
        }

        [Fact]
        public void Non_positive_equity_blocks_entry()
        {
            var guard = new RiskGuard(new RiskLimits { MaxDrawdownPercent = 0, MaxDailyLossPercent = 0 });
            guard.Initialise(10_000, Day1.Date);

            Assert.False(guard.EvaluateEntry(Snap(0)).Allowed);
        }

        [Fact]
        public void Observe_seeds_state_when_Initialise_was_never_called()
        {
            var guard = new RiskGuard(Limits());

            var decision = guard.Observe(Snap(10_000));

            Assert.True(decision.Allowed);
            Assert.Equal(10_000, guard.EquityPeak);
        }
    }
}
