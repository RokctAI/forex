using System;
using System.Linq;
using LondonBreakout.Core.Sessions;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    public class SessionScheduleTests
    {
        private static SessionSchedule Default(params DayOfWeek[] days)
        {
            var clock = new SessionClock(SessionClock.ResolveTimeZone("Europe/London"));
            return new SessionSchedule(
                clock,
                rangeStartHour: 0, rangeStartMinute: 0,
                signalHour: 9, signalMinute: 0,
                tradingDays: days.Length > 0 ? days : SessionSchedule.WeekdaysMondayToFriday.ToArray());
        }

        [Fact]
        public void Summer_window_spans_the_utc_day_boundary()
        {
            // 00:00 London on Wed 15 July 2026 (BST) is 23:00 UTC on Tue 14 July.
            // A naive implementation that treats the session date as a UTC date silently builds
            // the range from the wrong 9 hours.
            var window = Default().WindowFor(new DateTime(2026, 7, 15, 10, 0, 0, DateTimeKind.Utc));

            Assert.NotNull(window);
            Assert.Equal(new DateTime(2026, 7, 15), window.SessionDate);
            Assert.Equal(new DateTime(2026, 7, 14, 23, 0, 0, DateTimeKind.Utc), window.RangeStartUtc);
            Assert.Equal(new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc), window.SignalTimeUtc);
            Assert.Equal(TimeSpan.FromHours(9), window.Duration);
        }

        [Fact]
        public void Winter_window_lines_up_with_utc()
        {
            var window = Default().WindowFor(new DateTime(2026, 1, 14, 10, 0, 0, DateTimeKind.Utc));

            Assert.NotNull(window);
            Assert.Equal(new DateTime(2026, 1, 14, 0, 0, 0, DateTimeKind.Utc), window.RangeStartUtc);
            Assert.Equal(new DateTime(2026, 1, 14, 9, 0, 0, DateTimeKind.Utc), window.SignalTimeUtc);
        }

        [Fact]
        public void Weekend_is_not_a_trading_day_by_default()
        {
            // 18 July 2026 is a Saturday.
            var saturday = new DateTime(2026, 7, 18, 10, 0, 0, DateTimeKind.Utc);

            Assert.False(Default().IsTradingDay(saturday));
            Assert.Null(Default().WindowFor(saturday));
        }

        [Fact]
        public void Tuesday_only_configuration_rejects_other_weekdays()
        {
            var schedule = Default(DayOfWeek.Tuesday);

            Assert.True(schedule.IsTradingDay(new DateTime(2026, 7, 14, 10, 0, 0, DateTimeKind.Utc)));  // Tue
            Assert.False(schedule.IsTradingDay(new DateTime(2026, 7, 15, 10, 0, 0, DateTimeKind.Utc))); // Wed
        }

        [Fact]
        public void ActionableWindow_is_null_before_the_signal_and_set_afterwards()
        {
            var schedule = Default();

            // 07:59 UTC on 15 July 2026 is 08:59 London: one minute early.
            Assert.Null(schedule.ActionableWindow(new DateTime(2026, 7, 15, 7, 59, 0, DateTimeKind.Utc)));

            // 08:00 UTC is exactly 09:00 London.
            Assert.NotNull(schedule.ActionableWindow(new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc)));
        }

        [Fact]
        public void Signal_before_range_start_is_rejected_at_construction()
        {
            var clock = new SessionClock(SessionClock.ResolveTimeZone("Europe/London"));

            Assert.Throws<ArgumentException>(() => new SessionSchedule(
                clock, rangeStartHour: 10, rangeStartMinute: 0,
                signalHour: 9, signalMinute: 0,
                tradingDays: SessionSchedule.WeekdaysMondayToFriday));
        }

        [Fact]
        public void Empty_trading_days_is_rejected()
        {
            var clock = new SessionClock(SessionClock.ResolveTimeZone("Europe/London"));

            Assert.Throws<ArgumentException>(() => new SessionSchedule(
                clock, 0, 0, 9, 0, new DayOfWeek[0]));
        }

        [Theory]
        [InlineData("Mon,Tue,Wed,Thu,Fri", 5)]
        [InlineData("Tuesday", 1)]
        [InlineData("Tue", 1)]
        [InlineData("mon, wed , fri", 3)]
        [InlineData("Tue,Tue,Tue", 1)]
        public void ParseTradingDays_handles_the_usual_shapes(string input, int expectedCount)
        {
            Assert.Equal(expectedCount, SessionSchedule.ParseTradingDays(input).Count);
        }

        [Fact]
        public void ParseTradingDays_defaults_to_weekdays_when_blank()
        {
            Assert.Equal(5, SessionSchedule.ParseTradingDays("").Count);
            Assert.Equal(5, SessionSchedule.ParseTradingDays(null).Count);
        }

        [Fact]
        public void ParseTradingDays_rejects_garbage()
        {
            Assert.Throws<FormatException>(() => SessionSchedule.ParseTradingDays("Blursday"));
        }
    }
}
