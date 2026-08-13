// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

/// Forex domain SDK — the app surface for rule-based forex trading bots.
///
/// What it owns: the strategy catalog and the pinned-version model, resolved
/// risk parameters, and the broker-account dashboard shape.
///
/// What it deliberately does NOT own, per ADR-005: subscriptions, wallets,
/// plans and checkout. It imports only `base_sdk`; everything it needs from
/// another SDK is declared as a narrow abstract interface under
/// `domain/interface/` and satisfied by a host-owned adapter in
/// `templates/routes/forex_route_pages.dart`.
library forex_sdk;

// Models
export 'src/common/domain/models/money.dart';
export 'src/common/domain/models/forex_risk.dart';
export 'src/common/domain/models/forex_strategy.dart';
export 'src/common/domain/models/forex_account.dart';

// Consumer-owned interfaces (ADR-005). The host registers adapters for
// these; forex ships no implementations, only fail-closed stand-ins in
// ForexDependencies.
export 'src/common/domain/interface/forex_access_status_source.dart';
export 'src/common/domain/interface/forex_wallet_balance_source.dart';
export 'src/common/domain/interface/forex_plan_catalog.dart';
export 'src/common/domain/interface/forex_subscription_status_source.dart';

// forex's own backend seam
export 'src/common/domain/interface/forex_repository.dart';
export 'src/common/infrastructure/repositories/http_forex_repository.dart';

// Wiring + constants
export 'src/common/di/forex_di.dart';
export 'src/common/constants/forex_constants.dart';

// Screens
export 'src/common/presentation/pages/forex_strategy_list_page.dart';
export 'src/common/presentation/pages/forex_risk_preset_page.dart';
