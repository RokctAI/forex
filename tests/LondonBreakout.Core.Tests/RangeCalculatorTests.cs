using System;
using System.Collections.Generic;
using LondonBreakout.Core.Ranges;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    public class RangeCalculatorTests
    {
        private static readonly DateTime Start = new DateTime(2026, 7, 14, 23, 0, 0, DateTimeKind.Utc);
        private static readonly DateTime End = new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc);

        private static PriceBar Bar(DateTime open, double high, double low)
            => new PriceBar(open, (high + low) / 2, high, low, (high + low) / 2);

        [Fact]
        public void Takes_the_highest_high_and_lowest_low_in_the_window()
        {
            var bars = new List<PriceBar>
            {
                Bar(Start,                     1.1010, 1.0990),
                Bar(Start.AddHours(1),         1.1050, 1.0995),  // highest high
                Bar(Start.AddHours(2),         1.1020, 1.0960),  // lowest low
                Bar(Start.AddHours(3),         1.1030, 1.0980),
            };

            var range = new RangeCalculator(1).Compute(bars, Start, End);

            Assert.NotNull(range);
            Assert.Equal(1.1050, range.High, 6);
            Assert.Equal(1.0960, range.Low, 6);
            Assert.Equal(4, range.BarCount);
            Assert.Equal(0.0090, range.Height, 6);
            Assert.Equal(90.0, range.HeightInPips(0.0001), 4);
        }

        [Fact]
        public void Bar_opening_exactly_at_the_signal_time_is_excluded()
        {
            // This is the look-ahead guard. The 09:00 bar belongs to the period the bot is
            // about to trade; letting its high into the range would leak the future into the
            // entry level and make backtests look better than reality.
            var bars = new List<PriceBar>
            {
                Bar(Start,   1.1010, 1.0990),
                Bar(End,     1.9999, 1.0000),  // opens exactly at the boundary
            };

            var range = new RangeCalculator(1).Compute(bars, Start, End);

            Assert.NotNull(range);
            Assert.Equal(1.1010, range.High, 6);
            Assert.Equal(1.0990, range.Low, 6);
            Assert.Equal(1, range.BarCount);
        }

        [Fact]
        public void Bars_before_the_range_start_are_excluded()
        {
            var bars = new List<PriceBar>
            {
                Bar(Start.AddHours(-1), 1.9999, 1.0000),  // yesterday's session
                Bar(Start,              1.1010, 1.0990),
            };

            var range = new RangeCalculator(1).Compute(bars, Start, End);

            Assert.Equal(1, range.BarCount);
            Assert.Equal(1.1010, range.High, 6);
        }

        [Fact]
        public void Returns_null_when_there_are_fewer_bars_than_the_minimum()
        {
            var bars = new List<PriceBar> { Bar(Start, 1.1010, 1.0990) };

            Assert.Null(new RangeCalculator(minimumBars: 5).Compute(bars, Start, End));
        }

        [Fact]
        public void Returns_null_for_an_empty_series()
        {
            Assert.Null(new RangeCalculator(1).Compute(new List<PriceBar>(), Start, End));
        }

        [Fact]
        public void Rejects_an_inverted_window()
        {
            Assert.Throws<ArgumentException>(
                () => new RangeCalculator(1).Compute(new List<PriceBar>(), End, Start));
        }

        [Fact]
        public void Midpoint_sits_between_the_edges()
        {
            var bars = new List<PriceBar> { Bar(Start, 1.1000, 1.0900) };

            var range = new RangeCalculator(1).Compute(bars, Start, End);

            Assert.Equal(1.0950, range.Midpoint, 6);
        }
    }
}
