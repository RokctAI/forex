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

// Host-side route shell + cross-SDK adapters for forex_sdk.
//
// This file is HOST glue (installed into the app shell by the SDK
// installer), which is the one place allowed to import more than one
// feature SDK. forex_sdk owns the strategy/risk experience and declares
// what it needs from elsewhere as abstract interfaces; the adapters below
// satisfy those interfaces from whichever SDKs the app actually composes
// (ADR-005: consumer-owned interfaces, host-owned adapters).
//
// The wallet adapter is the one worth reading. forex declares
// ForexWalletBalanceSource — ONE read method — rather than depending on
// wallet_sdk's WalletRepositoryFacade, which bundles sendWalletBalance()
// and walletTopUp() alongside the reads. Forex reads the wallet and never
// writes to it; the adapter is where that boundary is actually held, and it
// is deliberately impossible to widen from inside forex_sdk.
//
// Every adapter here fails towards the closed/unknown answer. See each
// interface's doc comment for its documented safe default.

import 'package:auto_route/auto_route.dart';
import 'package:flutter/material.dart';
import 'package:forex_sdk/forex_sdk.dart';
import 'package:get_it/get_it.dart';

// The cross-SDK imports this file exists to hold are commented out rather
// than written speculatively:
//
//   import 'package:subscriptions_sdk/subscriptions_sdk.dart' as subs;
//   import 'package:wallet_sdk/wallet_sdk.dart' as wallet;
//
// Each adapter below is a TODO with its own fail-closed return value. The
// alternative — importing those SDKs and calling symbols guessed from their
// names — would produce a file that does not compile, and would look like
// working integration in a diff. The wiring is a host task with the real
// packages resolved; the shape it plugs into is what this file establishes.

/// Wire forex's own defaults plus the host adapters. Call once, early —
/// each route below also calls it defensively, which is idempotent.
void registerForexDependencies() {
  final getIt = GetIt.instance;
  ForexDependencies.register(getIt);

  if (!getIt.isRegistered<ForexAccessStatusSource>()) {
    getIt.registerLazySingleton<ForexAccessStatusSource>(
      () => _SubscriptionsAccessStatusAdapter(),
    );
  }
  if (!getIt.isRegistered<ForexWalletBalanceSource>()) {
    getIt.registerLazySingleton<ForexWalletBalanceSource>(
      () => _WalletBalanceAdapter(),
    );
  }
  if (!getIt.isRegistered<ForexSubscriptionStatusSource>()) {
    getIt.registerLazySingleton<ForexSubscriptionStatusSource>(
      () => _SubscriptionStatusAdapter(),
    );
  }
  if (!getIt.isRegistered<ForexPlanCatalog>()) {
    getIt.registerLazySingleton<ForexPlanCatalog>(() => _PlanCatalogAdapter());
  }
}

// ---------------------------------------------------------------------------
// Adapters
// ---------------------------------------------------------------------------

/// Derives forex's access level from the app's subscriptions facade.
///
/// TODO(host): map the app's real subscription tiers onto
/// ForexAccessLevel.standard / .pro. The mapping is app-specific — which
/// plan counts as "pro" is a pricing decision, not something forex_sdk can
/// know — so this adapter is intentionally left as the fail-closed
/// implementation rather than a guess.
///
/// It returns [ForexAccessLevel.none] until that mapping is written. That
/// is a locked UI, which is the correct placeholder for a paywall on a
/// product that trades real money: the alternative failure mode gives the
/// product away and starts a bot for somebody whose payment we did not
/// confirm. The server-side gate in `rforex.api.strategy.get_strategy`
/// refuses regardless, so this cannot be the only thing standing between a
/// user and a spec.
class _SubscriptionsAccessStatusAdapter implements ForexAccessStatusSource {
  @override
  Future<ForexAccessLevel> current() async => ForexAccessLevel.none;
}

/// The read-only half of the wallet, and only that half.
///
/// wallet_sdk's WalletRepositoryFacade is reachable from here — that is the
/// point of the host owning the adapter — but nothing forex_sdk can call
/// reaches the two money-moving methods on it.
class _WalletBalanceAdapter implements ForexWalletBalanceSource {
  // TODO(host): read the balance and its currency from wallet_sdk's facade.
  // Both halves are required — Money cannot be constructed without a
  // currency code, and that is deliberate: an amount whose currency was
  // never recorded cannot be recovered later.
  //
  // Until then: null, never Money(0, ...). A zero balance is a claim about
  // the user's money; an unread balance is a claim about the network. The
  // risk picker renders the difference (an em dash, not "R 0.00 per trade").
  @override
  Future<Money?> currentBalance() async => null;
}

/// Subscription lifecycle for the warning banners.
///
/// TODO(host): map the app's subscription record onto ForexSubscriptionStatus.
/// Returns `unknown` until then — no banner, and crucially no false
/// "payment failed" claim that would send a user to fix a card that is fine.
class _SubscriptionStatusAdapter implements ForexSubscriptionStatusSource {
  @override
  Future<ForexSubscriptionStatus> current() async =>
      ForexSubscriptionStatus.unknown;
}

/// Plans for the locked-card unlock path.
///
/// TODO(host): map the app's plan catalog onto ForexPlan, and route
/// [startCheckout] into payments_sdk's flow. Returns an empty list until
/// then, so a locked card says "plans unavailable" rather than showing a
/// placeholder price the user could not actually be charged.
class _PlanCatalogAdapter implements ForexPlanCatalog {
  @override
  Future<List<ForexPlan>> plansFor(ForexAccessLevel minimum) async => const [];

  @override
  Future<bool> startCheckout(String planId) async => false;
}

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------

/// The landing surface. forex_sdk declares itself the home SDK, so the
/// manifest's app_routes entry replaces the main route with this one.
@RoutePage(name: 'ForexStrategiesRoute')
class ForexStrategiesRouteView extends StatefulWidget {
  const ForexStrategiesRouteView({super.key});

  @override
  State<ForexStrategiesRouteView> createState() =>
      _ForexStrategiesRouteViewState();
}

class _ForexStrategiesRouteViewState extends State<ForexStrategiesRouteView> {
  @override
  void initState() {
    super.initState();
    registerForexDependencies();
  }

  @override
  Widget build(BuildContext context) {
    return ForexStrategyListPage(
      onOpen: (strategy) {
        // TODO(host): a strategy detail route. Not built — the detail
        // screen's centrepiece is the account dashboard, which has no
        // backend (no cTrader connector exists). Navigating to a screen of
        // blanks would be worse than not offering the tap.
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${strategy.title}: detail screen not built yet')),
        );
      },
      onUnlock: (_) => context.router.pushNamed('/subscribe'),
    );
  }
}

@RoutePage(name: 'ForexRiskRoute')
class ForexRiskRouteView extends StatefulWidget {
  const ForexRiskRouteView({super.key});

  @override
  State<ForexRiskRouteView> createState() => _ForexRiskRouteViewState();
}

class _ForexRiskRouteViewState extends State<ForexRiskRouteView> {
  @override
  void initState() {
    super.initState();
    registerForexDependencies();
  }

  @override
  Widget build(BuildContext context) => const ForexRiskPresetPage();
}

/// The account dashboard route.
///
/// NOT IMPLEMENTED, and visibly so. The backend endpoint
/// (`rforex.api.account.dashboard`) raises `NotImplementedError` because no
/// cTrader Open API client exists in this repository, and this screen says
/// that rather than rendering an empty dashboard with zeroes in it.
///
/// The arithmetic behind the numbers is finished and unit-tested
/// (`rforex.margin`); what is missing is the reading, and a screen that
/// showed a balance of 0.00 would be indistinguishable from an account with
/// no money in it.
@RoutePage(name: 'ForexAccountRoute')
class ForexAccountRouteView extends StatelessWidget {
  const ForexAccountRouteView({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.link_off, size: 40, color: theme.disabledColor),
              const SizedBox(height: 16),
              Text(
                'Account figures are unavailable.',
                style: theme.textTheme.titleMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'No broker connection is implemented yet, so there are no '
                'balance, equity or margin figures to show. Nothing here is '
                'estimated or placeholder — when this screen has numbers, '
                'they will be real ones.',
                style: theme.textTheme.bodySmall,
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
