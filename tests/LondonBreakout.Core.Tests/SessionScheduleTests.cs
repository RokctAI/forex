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
        public void ParseTradingDays_defaults_to_tuesday_only_when_blank()
        {
            // Clearing the parameter box must NOT silently widen the bot to five days a week.
            // Monday is an explicit stay-away day and the strategy trades Tuesdays, so the
            // fallback matches the shipped parameter default rather than the calendar.
            Assert.Equal(new[] { DayOfWeek.Tuesday }, SessionSchedule.ParseTradingDays(""));
            Assert.Equal(new[] { DayOfWeek.Tuesday }, SessionSchedule.ParseTradingDays(null));
        }

        [Fact]
        public void The_shipped_default_is_tuesday_alone()
        {
            Assert.Equal(new[] { DayOfWeek.Tuesday }, SessionSchedule.TuesdayOnly);

            // The parameter default string the cBot ships with must parse to the same thing.
            Assert.Equal(new[] { DayOfWeek.Tuesday }, SessionSchedule.ParseTradingDays("Tue"));
        }

        [Fact]
        public void Monday_is_not_a_trading_day_under_the_shipped_default()
        {
            // Monday is called out as a stay-away day, so this is a rule and not an accident of
            // the default. 13 July 2026 is a Monday; 14 July is the Tuesday.
            var schedule = Default(DayOfWeek.Tuesday);

            Assert.False(schedule.IsTradingDay(new DateTime(2026, 7, 13, 10, 0, 0, DateTimeKind.Utc)));
            Assert.Null(schedule.WindowFor(new DateTime(2026, 7, 13, 10, 0, 0, DateTimeKind.Utc)));

            Assert.True(schedule.IsTradingDay(new DateTime(2026, 7, 14, 10, 0, 0, DateTimeKind.Utc)));
        }

        [Fact]
        public void Every_non_tuesday_weekday_is_excluded_under_the_shipped_default()
        {
            // Mon 13 July 2026 through Fri 17 July 2026.
            var schedule = Default(DayOfWeek.Tuesday);

            for (var day = 13; day <= 17; day++)
            {
                var utc = new DateTime(2026, 7, day, 10, 0, 0, DateTimeKind.Utc);
                var expected = utc.DayOfWeek == DayOfWeek.Tuesday;

                Assert.Equal(expected, schedule.IsTradingDay(utc));
            }
        }

        [Fact]
        public void ParseTradingDays_rejects_garbage()
        {
            Assert.Throws<FormatException>(() => SessionSchedule.ParseTradingDays("Blursday"));
        }
    }
}
