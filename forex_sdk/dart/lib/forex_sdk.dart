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
