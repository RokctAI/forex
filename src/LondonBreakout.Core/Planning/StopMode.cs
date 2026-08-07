namespace LondonBreakout.Core.Planning
{
    /// <summary>
    /// How the protective stop distance is derived. The user never told us which rule he wants,
    /// so all three are implemented and the choice is a parameter. See the bot README's open
    /// questions section.
    /// </summary>
    public enum StopMode
    {
        /// <summary>
        /// Default. The stop sits on the far side of the range: a long entered above the range
        /// high is stopped out at the range low, and vice versa. Wide, but it is the level that
        /// actually invalidates the breakout thesis.
        /// </summary>
        OppositeRangeSide = 0,

        /// <summary>A fixed pip distance from the entry, ignoring range geometry.</summary>
        FixedPips = 1,

        /// <summary>A multiple of ATR, so the stop scales with recent volatility.</summary>
        AtrMultiple = 2,
    }
}
