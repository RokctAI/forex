using System;

namespace LondonBreakout.Core.Sessions
{
    /// <summary>
    /// Converts between UTC instants and wall-clock time in the strategy's session timezone.
    ///
    /// WHY THIS CLASS EXISTS
    /// ---------------------
    /// The strategy is defined in *London wall-clock* terms ("the range runs until 09:00").
    /// Three different clocks are in play and conflating any two of them silently breaks the
    /// bot for half the year:
    ///
    ///   1. Broker/server time. cTrader's <c>Server.Time</c> is expressed in whatever timezone
    ///      the cBot declares via <c>[Robot(TimeZone = ...)]</c>. Brokers are commonly on
    ///      EET/UTC+2/UTC+3, and many shift with their own DST calendar. It is NOT London time
    ///      and must never be assumed to be.
    ///   2. UTC. Stable, no DST, the only safe interchange format.
    ///   3. London civil time. UTC+0 in winter (GMT), UTC+1 in summer (BST). The BST switchover
    ///      dates are set by UK law and do NOT coincide with the US or EU broker DST dates.
    ///
    /// A fixed offset (e.g. "London = UTC+1") is wrong for roughly half the year and, worse,
    /// wrong by a variable amount during the weeks when different regions have switched and
    /// London has not. So we anchor everything to a real <see cref="TimeZoneInfo"/> and let the
    /// tz database resolve the offset for each specific instant.
    ///
    /// The bot therefore declares itself as UTC, takes <c>Server.TimeInUtc</c> as its only time
    /// source, and uses this class to answer "what is the London wall clock right now" and
    /// "what UTC instant is 09:00 London on this date".
    /// </summary>
    public sealed class SessionClock
    {
        private readonly TimeZoneInfo _timeZone;

        public SessionClock(TimeZoneInfo timeZone)
        {
            _timeZone = timeZone ?? throw new ArgumentNullException(nameof(timeZone));
        }

        public TimeZoneInfo TimeZone => _timeZone;

        /// <summary>
        /// Resolves a timezone id, accepting either a Windows id ("GMT Standard Time") or an
        /// IANA id ("Europe/London"). cTrader runs on Windows, where only Windows ids resolve
        /// natively; CI and unit tests run on Linux, where only IANA ids resolve natively.
        /// .NET 6 ships converters both ways, so we try the direct lookup first and then fall
        /// back to translating the id into the other convention. This keeps a single parameter
        /// value working on both platforms.
        /// </summary>
        public static TimeZoneInfo ResolveTimeZone(string id)
        {
            if (string.IsNullOrWhiteSpace(id))
                throw new ArgumentException("Timezone id must not be empty.", nameof(id));

            id = id.Trim();

            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(id);
            }
            catch (TimeZoneNotFoundException)
            {
                // Fall through to the cross-convention attempts below.
            }
            catch (InvalidTimeZoneException)
            {
                // Corrupt tz entry; treat the same as not found.
            }

            if (TimeZoneInfo.TryConvertIanaIdToWindowsId(id, out var windowsId))
            {
                try { return TimeZoneInfo.FindSystemTimeZoneById(windowsId); }
                catch (TimeZoneNotFoundException) { }
            }

            if (TimeZoneInfo.TryConvertWindowsIdToIanaId(id, out var ianaId))
            {
                try { return TimeZoneInfo.FindSystemTimeZoneById(ianaId); }
                catch (TimeZoneNotFoundException) { }
            }

            throw new TimeZoneNotFoundException(
                $"Could not resolve timezone '{id}' as either a Windows id (e.g. 'GMT Standard Time') " +
                "or an IANA id (e.g. 'Europe/London').");
        }

        /// <summary>Wall-clock time in the session timezone for a given UTC instant.</summary>
        public DateTime ToSessionTime(DateTime utc)
        {
            return TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), _timeZone);
        }

        /// <summary>The session-local calendar date for a given UTC instant.</summary>
        public DateTime SessionDateOf(DateTime utc) => ToSessionTime(utc).Date;

        /// <summary>
        /// Converts a session-local wall-clock time to the UTC instant it denotes.
        ///
        /// DST edge cases are resolved explicitly rather than left to chance:
        ///
        ///  * Spring-forward gap (the local time never happens — 01:30 on the BST switch date):
        ///    we roll forward by the DST delta, so a session time inside the gap lands on the
        ///    first instant that actually exists. A range boundary that vanishes for one day a
        ///    year must not throw or silently return a wrong instant.
        ///
        ///  * Autumn fall-back ambiguity (the local time happens twice): we deliberately take
        ///    the FIRST (still-DST) occurrence. Either choice is defensible; what matters is
        ///    that it is deterministic and documented, so backtests and live runs agree.
        ///
        /// Neither case touches 09:00 London in practice — UK transitions happen at 01:00/02:00 —
        /// but the range start is configurable and defaults to 00:00, which sits far closer to
        /// the transition, so the handling is real rather than theoretical.
        /// </summary>
        public DateTime SessionLocalToUtc(DateTime sessionLocal)
        {
            var naive = DateTime.SpecifyKind(sessionLocal, DateTimeKind.Unspecified);

            if (_timeZone.IsInvalidTime(naive))
            {
                var adjustment = GetSpringForwardDelta(naive);
                naive = naive.Add(adjustment);
            }

            if (_timeZone.IsAmbiguousTime(naive))
            {
                // Pick the first occurrence: the offset still in effect *before* the clocks go back.
                var offsets = _timeZone.GetAmbiguousTimeOffsets(naive);
                var chosen = offsets[0];
                foreach (var offset in offsets)
                {
                    if (offset > chosen) chosen = offset;
                }
                return DateTime.SpecifyKind(naive - chosen, DateTimeKind.Utc);
            }

            return TimeZoneInfo.ConvertTimeToUtc(naive, _timeZone);
        }

        /// <summary>
        /// Size of the spring-forward gap containing <paramref name="invalidLocal"/>. Almost
        /// always one hour, but Lord Howe Island uses 30 minutes and historical zones have used
        /// other values, so we measure it rather than hardcoding an hour.
        /// </summary>
        private TimeSpan GetSpringForwardDelta(DateTime invalidLocal)
        {
            var dayStart = invalidLocal.Date;
            var beforeUtc = TimeZoneInfo.ConvertTimeToUtc(
                DateTime.SpecifyKind(dayStart, DateTimeKind.Unspecified), _timeZone);

            var offsetBefore = _timeZone.GetUtcOffset(beforeUtc);
            var offsetAfter = _timeZone.GetUtcOffset(beforeUtc.AddDays(1));

            var delta = offsetAfter - offsetBefore;
            return delta > TimeSpan.Zero ? delta : TimeSpan.FromHours(1);
        }

        /// <summary>
        /// The UTC instant of a given hour:minute on the session-local date that
        /// <paramref name="utcReference"/> falls on.
        /// </summary>
        public DateTime SessionTimeOnDateOf(DateTime utcReference, int hour, int minute)
        {
            var date = SessionDateOf(utcReference);
            return SessionLocalToUtc(date.AddHours(hour).AddMinutes(minute));
        }
    }
}
