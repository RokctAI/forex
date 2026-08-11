using System;

namespace LondonBreakout.Core.Planning
{
    /// <summary>
    /// One leg of the straddle, fully specified in price terms before anything is sent to the
    /// broker. Everything the bot needs to place a protected pending order lives here.
    /// </summary>
    public sealed class BreakoutLeg
    {
        public BreakoutLeg(bool isBuy, double entryPrice, double stopLossPrice, double takeProfitPrice)
        {
            IsBuy = isBuy;
            EntryPrice = entryPrice;
            StopLossPrice = stopLossPrice;
            TakeProfitPrice = takeProfitPrice;

            if (isBuy)
            {
                if (stopLossPrice >= entryPrice)
                    throw new ArgumentException("A long's stop must sit below its entry.", nameof(stopLossPrice));
                if (takeProfitPrice <= entryPrice)
                    throw new ArgumentException("A long's target must sit above its entry.", nameof(takeProfitPrice));
            }
            else
            {
                if (stopLossPrice <= entryPrice)
                    throw new ArgumentException("A short's stop must sit above its entry.", nameof(stopLossPrice));
                if (takeProfitPrice >= entryPrice)
                    throw new ArgumentException("A short's target must sit below its entry.", nameof(takeProfitPrice));
            }
        }

        public bool IsBuy { get; }
        public double EntryPrice { get; }
        public double StopLossPrice { get; }
        public double TakeProfitPrice { get; }

        /// <summary>Absolute stop distance in price terms. Always positive.</summary>
        public double StopDistance => Math.Abs(EntryPrice - StopLossPrice);

        /// <summary>Absolute target distance in price terms. Always positive.</summary>
        public double TargetDistance => Math.Abs(TakeProfitPrice - EntryPrice);

        public double StopDistanceInPips(double pipSize) => StopDistance / pipSize;
        public double TargetDistanceInPips(double pipSize) => TargetDistance / pipSize;

        public override string ToString()
            => $"{(IsBuy ? "BUY STOP" : "SELL STOP")} @{EntryPrice} SL={StopLossPrice} TP={TakeProfitPrice}";
    }

    /// <summary>
    /// The full two-sided plan for one session: a buy stop above the range and a sell stop
    /// below it. Either leg may be absent if a rejection reason applies to it.
    /// </summary>
    public sealed class BreakoutPlan
    {
        private BreakoutPlan(BreakoutLeg buyLeg, BreakoutLeg sellLeg, string rejectionReason)
        {
            BuyLeg = buyLeg;
            SellLeg = sellLeg;
            RejectionReason = rejectionReason;
        }

        public BreakoutLeg BuyLeg { get; }
        public BreakoutLeg SellLeg { get; }

        /// <summary>Non-null when no legs were produced; explains why, for the log.</summary>
        public string RejectionReason { get; }

        public bool HasLegs => BuyLeg != null || SellLeg != null;

        public static BreakoutPlan Straddle(BreakoutLeg buyLeg, BreakoutLeg sellLeg)
            => new BreakoutPlan(buyLeg, sellLeg, null);

        public static BreakoutPlan Rejected(string reason)
            => new BreakoutPlan(null, null, reason ?? "unspecified");
    }
}
