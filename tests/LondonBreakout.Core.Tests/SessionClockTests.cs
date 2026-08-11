using System;
using LondonBreakout.Core.Sessions;
using Xunit;

namespace LondonBreakout.Core.Tests
{
    /// <summary>
    /// These are the tests that matter most. A breakout bot that thinks 09:00 London is 09:00
    /// UTC trades an hour late for seven months of the year, and the failure is silent: the bot
    /// still places orders, they are just placed against the wrong range.
    /// </summary>
    public class SessionClockTests
    {
        // UK DST in 2026: BST runs 29 March to 25 October.
        private static readonly TimeZoneInfo London = SessionClock.ResolveTimeZone("Europe/London");

        private static SessionClock Clock() => new SessionClock(London);

        [Theory]
        [InlineData("Europe/London")]
        [InlineData("GMT Standard Time")]
        public void ResolveTimeZone_accepts_both_iana_and_windows_ids(string id)
        {
            // cTrader runs on Windows and only resolves Windows ids natively; CI runs on Linux
            // and only resolves IANA ids natively. One parameter value has to work on both.
            var tz = SessionClock.ResolveTimeZone(id);

            Assert.Equal(TimeSpan.Zero, tz.GetUtcOffset(new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc)));
            Assert.Equal(TimeSpan.FromHours(1), tz.GetUtcOffset(new DateTime(2026, 7, 15, 12, 0, 0, DateTimeKind.Utc)));
        }

        [Fact]
        public void ResolveTimeZone_throws_on_nonsense()
        {
            Assert.Throws<TimeZoneNotFoundException>(() => SessionClock.ResolveTimeZone("Middle/Earth"));
        }

        [Fact]
        public void Winter_0900_London_is_0900_utc()
        {
            var utc = Clock().SessionLocalToUtc(new DateTime(2026, 1, 15, 9, 0, 0));
            Assert.Equal(new DateTime(2026, 1, 15, 9, 0, 0, DateTimeKind.Utc), utc);
        }

        [Fact]
        public void Summer_0900_London_is_0800_utc()
        {
            // The whole reason TimeZoneInfo is used instead of a fixed offset.
            var utc = Clock().SessionLocalToUtc(new DateTime(2026, 7, 15, 9, 0, 0));
            Assert.Equal(new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc), utc);
        }

        [Fact]
        public void Signal_time_shifts_by_an_hour_across_the_bst_boundary()
        {
            var clock = Clock();

            // 27 March 2026 is GMT; 30 March 2026 is BST. Same wall clock, different UTC instant.
            var beforeSwitch = clock.SessionLocalToUtc(new DateTime(2026, 3, 27, 9, 0, 0));
            var afterSwitch = clock.SessionLocalToUtc(new DateTime(2026, 3, 30, 9, 0, 0));

            Assert.Equal(9, beforeSwitch.Hour);
            Assert.Equal(8, afterSwitch.Hour);
        }

        [Fact]
        public void ToSessionTime_is_the_inverse_of_SessionLocalToUtc()
        {
            var clock = Clock();
            var local = new DateTime(2026, 7, 15, 9, 0, 0);

            var roundTripped = clock.ToSessionTime(clock.SessionLocalToUtc(local));

            Assert.Equal(local, roundTripped);
        }

        [Fact]
        public void Invalid_local_time_in_the_spring_forward_gap_rolls_forward()
        {
            // 01:30 on 29 March 2026 never happens: the clocks jump 01:00 -> 02:00.
            // Rolling forward by the gap gives 02:30 BST, which is 01:30 UTC.
            var utc = Clock().SessionLocalToUtc(new DateTime(2026, 3, 29, 1, 30, 0));

            Assert.Equal(new DateTime(2026, 3, 29, 1, 30, 0, DateTimeKind.Utc), utc);
        }

        [Fact]
        public void Ambiguous_local_time_at_fall_back_picks_the_first_occurrence()
        {
            // 01:30 on 25 October 2026 happens twice. We documented that we take the first
            // (still BST, UTC+1), which is 00:30 UTC.
            var utc = Clock().SessionLocalToUtc(new DateTime(2026, 10, 25, 1, 30, 0));

            Assert.Equal(new DateTime(2026, 10, 25, 0, 30, 0, DateTimeKind.Utc), utc);
        }

        [Fact]
        public void SessionDateOf_uses_london_midnight_not_utc_midnight()
        {
            // 23:30 UTC on 14 July is already 00:30 on 15 July in London (BST).
            // Getting this wrong assigns the whole overnight range to the wrong session.
            var utc = new DateTime(2026, 7, 14, 23, 30, 0, DateTimeKind.Utc);

            Assert.Equal(new DateTime(2026, 7, 15), Clock().SessionDateOf(utc));
        }

        [Fact]
        public void SessionTimeOnDateOf_anchors_to_the_session_local_date()
        {
            var utcReference = new DateTime(2026, 7, 14, 23, 30, 0, DateTimeKind.Utc);

            var signal = Clock().SessionTimeOnDateOf(utcReference, 9, 0);

            // London-local 15 July 09:00 == 08:00 UTC on 15 July.
            Assert.Equal(new DateTime(2026, 7, 15, 8, 0, 0, DateTimeKind.Utc), signal);
        }
    }
}
