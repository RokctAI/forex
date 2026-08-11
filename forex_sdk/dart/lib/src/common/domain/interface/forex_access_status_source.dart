// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

/// The user's entitlement standing, as forex needs it.
///
/// Three states, not a bool. The catalog has to say different things to
/// somebody who has never subscribed, somebody whose subscription lapsed,
/// and somebody who pays but at the wrong tier — and telling a paying user
/// to "subscribe" is the kind of mistake they notice immediately.
enum ForexAccessLevel {
  /// No subscription covers today. Sell a subscription.
  none,

  /// Covered today at the standard tier.
  standard,

  /// Covered today at the top tier.
  pro;

  bool get isActive => this != ForexAccessLevel.none;

  bool meets(ForexAccessLevel required) => index >= required.index;

  static ForexAccessLevel parse(Object? raw) {
    switch (raw) {
      case 'pro':
        return ForexAccessLevel.pro;
      case 'standard':
        return ForexAccessLevel.standard;
      default:
        return ForexAccessLevel.none;
    }
  }
}

/// Consumer-owned source of the user's [ForexAccessLevel].
///
/// **Why this exists.** ADR-005: forex_sdk may import `base_sdk` and nothing
/// else. It needs to know whether a user's subscription is live, but that
/// knowledge lives in `subscriptions_sdk`, and importing it would couple
/// two feature SDKs directly. So forex declares the narrow shape it needs
/// here, and the host app registers an adapter that derives it from
/// whatever subscriptions facade the app actually composes. The same
/// interface is satisfied by the rforex backend's own `my_entitlements`
/// endpoint when no subscriptions SDK is present — which is exactly the
/// point of owning the interface rather than the dependency.
///
/// **Safe default on failure.** [ForexAccessLevel.none]. If [current]
/// throws, times out, or the adapter is not registered at all, callers must
/// treat the user as unentitled. Failing open on a paywall for a product
/// that trades real money would be bad twice over: it gives away the
/// product, and it starts a bot for somebody whose payment status we could
/// not confirm.
///
/// Note that this interface gates the UI only. The real enforcement is
/// server-side in `rforex.api.strategy.get_strategy`, which will refuse a
/// spec regardless of what any client believes.
abstract class ForexAccessStatusSource {
  /// Prefer a cached last-known-good answer over failing offline — but
  /// prefer failing over guessing upward. Implementations should never
  /// return a level higher than one they have actually observed.
  Future<ForexAccessLevel> current();
}
