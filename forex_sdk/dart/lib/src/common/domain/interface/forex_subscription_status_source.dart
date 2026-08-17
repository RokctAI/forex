// Copyright (c) 2026 RokctAI
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

/// The lifecycle facts about a subscription that forex needs but
/// entitlement alone cannot express.
///
/// [ForexAccessStatusSource] answers "may this user run a bot right now",
/// which is the gating question. This answers the adjacent operational
/// ones — is it about to lapse, did the last payment fail, is it set to
/// cancel — which forex needs because a bot that stops when a card expires
/// looks to the user exactly like a bot that broke.
class ForexSubscriptionStatus {
  /// A subscription covers today.
  final bool active;

  /// When cover ends, if known. Null means unknown, NOT "never" — an
  /// unknown renewal date must not be rendered as an open-ended one.
  final DateTime? currentPeriodEnd;

  /// The user has cancelled but cover has not ended yet. The bot keeps
  /// running until it does; the UI warns.
  final bool cancelAtPeriodEnd;

  /// The last renewal attempt failed. Distinct from lapsed: the user still
  /// has cover, and this is a fixable problem they can act on today.
  final bool paymentFailed;

  const ForexSubscriptionStatus({
    required this.active,
    required this.currentPeriodEnd,
    required this.cancelAtPeriodEnd,
    required this.paymentFailed,
  });

  /// The safe default: not active, nothing known, no alarming claims.
  ///
  /// Note what it does NOT say — it does not claim a payment failed
  /// (which would send the user to fix a card that is fine) and it does not
  /// claim an end date. Unknown is represented as unknown.
  static const ForexSubscriptionStatus unknown = ForexSubscriptionStatus(
    active: false,
    currentPeriodEnd: null,
    cancelAtPeriodEnd: false,
    paymentFailed: false,
  );
}

/// Consumer-owned source of subscription lifecycle state.
///
/// **Why this exists.** ADR-005: this SDK imports only `base_sdk`.
/// Subscription lifecycle lives in `subscriptions_sdk`, and the host
/// registers an adapter. It is a separate interface from
/// [ForexAccessStatusSource] rather than extra fields on it, because the two
/// have different failure consequences: an access level that fails wrong
/// starts or blocks a trading bot, while a renewal date that fails wrong
/// shows the wrong banner. Keeping them apart means the strict fail-closed
/// rule stays attached to the one that needs it, and an adapter that can
/// only answer one of them can register just that one.
///
/// **Safe default on failure.** [ForexSubscriptionStatus.unknown], and no
/// banner at all. This interface must never be the reason a bot stops —
/// gating is [ForexAccessStatusSource]'s job, enforced server-side. The
/// worst outcome of this one failing is that a user is not warned early
/// about a lapse, which is a missed nicety rather than an unauthorised
/// trade.
abstract class ForexSubscriptionStatusSource {
  Future<ForexSubscriptionStatus> current();
}
