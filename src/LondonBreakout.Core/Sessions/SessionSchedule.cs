using System;
using System.Collections.Generic;
using System.Linq;

namespace LondonBreakout.Core.Sessions
{
    /// <summary>
    /// Turns the configured session times ("range from 00:00, signal at 09:00, Mon-Fri") into
    /// concrete UTC instants for a given day, via <see cref="SessionClock"/>.
    ///
    /// Pure logic: no cTrader types, so this is directly unit-testable including across the
    /// BST/GMT boundary.
    /// </summary>
    public sealed class SessionSchedule
    {
        private readonly SessionClock _clock;
        private readonly HashSet<DayOfWeek> _tradingDays;

        public SessionSchedule(
            SessionClock clock,
            int rangeStartHour,
            int rangeStartMinute,
            int signalHour,
            int signalMinute,
            IEnumerable<DayOfWeek> tradingDays)
        {
            _clock = clock ?? throw new ArgumentNullException(nameof(clock));

            ValidateTimeOfDay(rangeStartHour, rangeStartMinute, nameof(rangeStartHour));
            ValidateTimeOfDay(signalHour, signalMinute, nameof(signalHour));

            RangeStartHour = rangeStartHour;
            RangeStartMinute = rangeStartMinute;
            SignalHour = signalHour;
            SignalMinute = signalMinute;

            _tradingDays = new HashSet<DayOfWeek>(tradingDays ?? Enumerable.Empty<DayOfWeek>());
            if (_tradingDays.Count == 0)
                throw new ArgumentException("At least one trading day must be configured.", nameof(tradingDays));

            if (signalHour * 60 + signalMinute <= rangeStartHour * 60 + rangeStartMinute)
            {
                throw new ArgumentException(
                    $"Signal time {signalHour:00}:{signalMinute:00} must be later in the day than " +
                    $"range start {rangeStartHour:00}:{rangeStartMinute:00}. Overnight ranges that wrap " +
                    "past midnight are not supported in this version.");
            }
        }

        public int RangeStartHour { get; }
        public int RangeStartMinute { get; }
        public int SignalHour { get; }
        public int SignalMinute { get; }

        public IReadOnlyCollection<DayOfWeek> TradingDays => _tradingDays;

        private static void ValidateTimeOfDay(int hour, int minute, string paramName)
        {
            if (hour < 0 || hour > 23)
                throw new ArgumentOutOfRangeException(paramName, hour, "Hour must be 0-23.");
            if (minute < 0 || minute > 59)
                throw new ArgumentOutOfRangeException(paramName, minute, "Minute must be 0-59.");
        }

        /// <summary>Is the session-local date of this UTC instant a configured trading day?</summary>
        public bool IsTradingDay(DateTime utcNow)
        {
            return _tradingDays.Contains(_clock.SessionDateOf(utcNow).DayOfWeek);
        }

        /// <summary>
        /// The session window for the session-local day containing <paramref name="utcNow"/>,
        /// or null when that day is not a configured trading day.
        /// </summary>
        public SessionWindow WindowFor(DateTime utcNow)
        {
            if (!IsTradingDay(utcNow)) return null;

            var sessionDate = _clock.SessionDateOf(utcNow);

            var rangeStartUtc = _clock.SessionLocalToUtc(
                sessionDate.AddHours(RangeStartHour).AddMinutes(RangeStartMinute));

            var signalUtc = _clock.SessionLocalToUtc(
                sessionDate.AddHours(SignalHour).AddMinutes(SignalMinute));

            return new SessionWindow(sessionDate, rangeStartUtc, signalUtc);
        }

        /// <summary>
        /// Convenience for the bot's polling loop: the window for today if today is a trading
        /// day AND the signal time has already passed; otherwise null. This is the single
        /// question the strategy asks on every timer tick.
        /// </summary>
        public SessionWindow ActionableWindow(DateTime utcNow)
        {
            var window = WindowFor(utcNow);
            if (window == null) return null;
            return window.IsRangeComplete(utcNow) ? window : null;
        }

        public static IReadOnlyList<DayOfWeek> WeekdaysMondayToFriday { get; } = new[]
        {
            DayOfWeek.Monday,
            DayOfWeek.Tuesday,
            DayOfWeek.Wednesday,
            DayOfWeek.Thursday,
            DayOfWeek.Friday,
        };

        /// <summary>
        /// Parses a comma-separated day list such as "Mon,Tue,Wed,Thu,Fri" or "Tuesday".
        /// Used to expose <c>TradingDays</c> as a single cTrader string parameter, because the
        /// cTrader parameter system has no native multi-select control.
        /// </summary>
        public static IReadOnlyList<DayOfWeek> ParseTradingDays(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                return WeekdaysMondayToFriday;

            var result = new List<DayOfWeek>();
            foreach (var raw in value.Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var token = raw.Trim();
                if (token.Length == 0) continue;

                if (Enum.TryParse<DayOfWeek>(token, ignoreCase: true, out var day))
                {
                    if (!result.Contains(day)) result.Add(day);
                    continue;
                }

                var matched = false;
                foreach (DayOfWeek candidate in Enum.GetValues(typeof(DayOfWeek)))
                {
                    if (candidate.ToString().StartsWith(token, StringComparison.OrdinalIgnoreCase))
                    {
                        if (!result.Contains(candidate)) result.Add(candidate);
                        matched = true;
                        break;
                    }
                }

                if (!matched)
                    throw new FormatException($"'{token}' is not a recognised day of the week.");
            }

            if (result.Count == 0)
                throw new FormatException($"No valid days parsed from '{value}'.");

            return result;
        }
    }
}
