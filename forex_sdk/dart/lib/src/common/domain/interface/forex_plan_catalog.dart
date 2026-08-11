// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

import '../models/money.dart';
import 'forex_access_status_source.dart';

/// A purchasable plan, as forex needs to display it.
///
/// The price is a [Money], so a plan cannot be rendered without its
/// currency. A subscription price shown as a bare number is the same defect
/// as an account balance shown as a bare number, and it is worse here
/// because the user is about to agree to it.
class ForexPlan {
  /// Opaque identifier the host's checkout understands. forex never parses
  /// it — that would be reaching into the payments SDK's model through a
  /// string.
  final String id;

  final String title;
  final String? description;
  final Money price;

  /// The billing period, as a display string supplied by the host
  /// ('per month', 'per year'). Deliberately not an enum: forex has no
  /// opinion about billing periods and enumerating them here would mean
  /// this SDK needed changing whenever the pricing model did.
  final String periodLabel;

  /// The access level buying this grants — the join between the payments
  /// world and forex's own gating.
  final ForexAccessLevel grants;

  const ForexPlan({
    required this.id,
    required this.title,
    required this.description,
    required this.price,
    required this.periodLabel,
    required this.grants,
  });
}

/// Consumer-owned source of purchasable plans.
///
/// **Why this exists.** ADR-005: forex_sdk imports only `base_sdk`. Plans
/// and checkout belong to `payments_sdk`/`subscriptions_sdk`; the host app
/// registers an adapter that maps whichever of those it composes onto this
/// shape. Forex needs plans for exactly one purpose — showing a locked
/// strategy card what it would take to unlock it — and it needs nothing
/// else from the payments world.
///
/// Note there is no `purchase` method here. Starting a checkout is the
/// host's job: it owns the payment SDK, the platform store rules and the
/// receipt handling, none of which forex should have an opinion about.
/// [startCheckout] returns a callback-free future that completes when the
/// host's flow is done, and forex simply re-reads entitlement afterwards.
///
/// **Safe default on failure.** An empty plan list, and a locked card that
/// says plans are unavailable right now. Never a hardcoded fallback price —
/// showing a price the user cannot actually be charged is worse than
/// showing none, and any placeholder would eventually be wrong.
abstract class ForexPlanCatalog {
  /// Plans that would grant at least [minimum]. Returns an empty list when
  /// the catalog cannot be read; the caller renders "unavailable", not an
  /// empty shop.
  Future<List<ForexPlan>> plansFor(ForexAccessLevel minimum);

  /// Hand off to the host's checkout for [planId].
  ///
  /// Completes with true only if the host is confident the purchase
  /// succeeded. Anything else — cancelled, failed, unknown — completes
  /// false, and forex re-checks entitlement with the server rather than
  /// believing the client.
  Future<bool> startCheckout(String planId);
}
