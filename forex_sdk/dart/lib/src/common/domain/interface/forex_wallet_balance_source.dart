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

import '../models/money.dart';

/// Read-only view of the user's in-app wallet balance.
///
/// **Why this exists, and why it is not `WalletRepositoryFacade`.** ADR-005
/// forbids forex_sdk from importing `wallet_sdk`, but the more specific
/// reason is the shape of the thing on the other side. `WalletRepositoryFacade`
/// bundles four methods, two of which move money:
/// `sendWalletBalance(userUuid, amount)` and `walletTopUp(...)`. Depending on
/// it would put two money-moving writes inside the reach of every screen in
/// this SDK, for the sake of reading one number.
///
/// **Forex reads the wallet and never writes to it.** Subscriptions are paid
/// through the payments/subscriptions flow, not from here; trading capital
/// lives at the broker, not in the wallet. There is no forex feature that
/// legitimately debits or credits a wallet, so there is no method here that
/// can. This interface is one method wide by design, and widening it is a
/// decision somebody has to make deliberately rather than inherit.
///
/// **Safe default on failure.** `null`. A wallet balance that could not be
/// read is unknown, and the UI must render it as unknown — never as zero. A
/// zero balance is a claim about the user's money; an unread balance is a
/// claim about the network. Screens that show a derived consequence from a
/// balance (the risk picker) must show the formula and an em dash rather
/// than compute a consequence from a fabricated figure.
abstract class ForexWalletBalanceSource {
  /// The current wallet balance, with its currency, or null when it cannot
  /// be determined.
  ///
  /// Never throws for an ordinary failure — returning null is the contract,
  /// so that a caller cannot forget the try/catch and end up rendering an
  /// error where a dash belongs.
  Future<Money?> currentBalance();
}
