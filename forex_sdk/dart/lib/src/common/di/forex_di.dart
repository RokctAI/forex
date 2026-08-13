// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

import 'package:get_it/get_it.dart';

import '../domain/interface/forex_access_status_source.dart';
import '../domain/interface/forex_plan_catalog.dart';
import '../domain/interface/forex_repository.dart';
import '../domain/interface/forex_subscription_status_source.dart';
import '../domain/interface/forex_wallet_balance_source.dart';
import '../domain/models/money.dart';
import '../infrastructure/repositories/http_forex_repository.dart';

/// Dependency wiring for forex_sdk.
///
/// Two kinds of dependency live here and they are registered differently:
///
/// - **forex's own backend** ([ForexRepository]) gets a real default. It is
///   this SDK's own module; there is nothing for a host to supply.
/// - **The four consumer-owned interfaces** (ADR-005) get NO default. They
///   describe things that live in other SDKs, and forex cannot construct
///   them. The host app registers adapters in
///   `templates/routes/forex_route_pages.dart`.
///
/// The second group is why the resolvers below exist. A screen never calls
/// `GetIt.instance<ForexAccessStatusSource>()` directly, because that throws
/// when nothing is registered — and a paywall screen crashing is not the
/// same as a paywall screen locking. Each resolver returns a documented
/// **safe fallback** instead, and every one of those fallbacks is the
/// closed/unknown direction:
///
/// | Interface | Unregistered behaviour |
/// |---|---|
/// | [ForexAccessStatusSource] | `ForexAccessLevel.none` — everything locked |
/// | [ForexWalletBalanceSource] | `null` balance — rendered as unknown, never zero |
/// | [ForexPlanCatalog] | empty catalog — "plans unavailable", never a fake price |
/// | [ForexSubscriptionStatusSource] | `unknown` — no banner, no false alarm |
///
/// An app that composes forex_sdk and registers none of them therefore gets
/// a fully locked, honest UI rather than a broken or an accidentally open
/// one.
class ForexDependencies {
  const ForexDependencies._();

  /// Register forex's own defaults. Idempotent — safe to call from every
  /// route's `initState`, which is how the lms precedent does it.
  ///
  /// Deliberately does NOT register the four consumer-owned interfaces.
  /// Registering a stub for them here would mean a host that forgot to wire
  /// its adapter silently got the stub's answers, and the whole point of
  /// ADR-005 is that the host supplies those.
  static void register(GetIt getIt) {
    if (!getIt.isRegistered<ForexRepository>()) {
      getIt.registerLazySingleton<ForexRepository>(
        () => HttpForexRepository(),
      );
    }
  }

  static ForexRepository repository([GetIt? from]) {
    final getIt = from ?? GetIt.instance;
    register(getIt);
    return getIt<ForexRepository>();
  }

  /// The registered access source, or a fail-closed stand-in.
  static ForexAccessStatusSource accessStatus([GetIt? from]) {
    final getIt = from ?? GetIt.instance;
    if (getIt.isRegistered<ForexAccessStatusSource>()) {
      return getIt<ForexAccessStatusSource>();
    }
    return const _LockedAccessStatusSource();
  }

  static ForexWalletBalanceSource walletBalance([GetIt? from]) {
    final getIt = from ?? GetIt.instance;
    if (getIt.isRegistered<ForexWalletBalanceSource>()) {
      return getIt<ForexWalletBalanceSource>();
    }
    return const _UnknownWalletBalanceSource();
  }

  static ForexPlanCatalog plans([GetIt? from]) {
    final getIt = from ?? GetIt.instance;
    if (getIt.isRegistered<ForexPlanCatalog>()) {
      return getIt<ForexPlanCatalog>();
    }
    return const _EmptyPlanCatalog();
  }

  static ForexSubscriptionStatusSource subscriptionStatus([GetIt? from]) {
    final getIt = from ?? GetIt.instance;
    if (getIt.isRegistered<ForexSubscriptionStatusSource>()) {
      return getIt<ForexSubscriptionStatusSource>();
    }
    return const _UnknownSubscriptionStatusSource();
  }
}

/// Everything locked. The correct answer when the host has not wired an
/// entitlement adapter: this product trades real money, so an unknown
/// payment status must not start a bot.
class _LockedAccessStatusSource implements ForexAccessStatusSource {
  const _LockedAccessStatusSource();

  @override
  Future<ForexAccessLevel> current() async => ForexAccessLevel.none;
}

/// Balance unknown. Note the return of `null` rather than `Money(0, ...)` —
/// a zero balance is a claim about the user's money, and this stand-in has
/// no basis for making one.
class _UnknownWalletBalanceSource implements ForexWalletBalanceSource {
  const _UnknownWalletBalanceSource();

  @override
  Future<Money?> currentBalance() async => null;
}

/// No plans. A locked card says "plans unavailable" rather than showing a
/// placeholder price the user could not actually be charged.
class _EmptyPlanCatalog implements ForexPlanCatalog {
  const _EmptyPlanCatalog();

  @override
  Future<List<ForexPlan>> plansFor(ForexAccessLevel minimum) async => const [];

  @override
  Future<bool> startCheckout(String planId) async => false;
}

/// Nothing known, and nothing alarming claimed — no "payment failed" banner
/// for a card that is fine.
class _UnknownSubscriptionStatusSource
    implements ForexSubscriptionStatusSource {
  const _UnknownSubscriptionStatusSource();

  @override
  Future<ForexSubscriptionStatus> current() async =>
      ForexSubscriptionStatus.unknown;
}
