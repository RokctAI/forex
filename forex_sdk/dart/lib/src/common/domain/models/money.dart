// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

/// An amount and the currency it is denominated in, together.
///
/// Every monetary value in this SDK is a [Money], never a bare `double`.
/// The rule it enforces: **a currency code is persisted and carried next to
/// every amount**, because it cannot be recovered afterwards. An amount of
/// 4,812.55 whose currency was never recorded is not a value — the account
/// currency at the time is not derivable from anything else, and by the
/// time anyone notices, the reading it came from is gone.
///
/// Nothing upstream in the estate does this, which is exactly why forex
/// starts with it rather than retrofitting it.
class Money {
  /// The numeric amount. May be negative — an unrealised loss and a negative
  /// free margin are both real, and clamping either would hide a margin call.
  final double amount;

  /// ISO 4217 code, uppercased. Never empty: [Money] cannot be constructed
  /// without one.
  final String currencyCode;

  const Money._(this.amount, this.currencyCode);

  /// Construct from a validated pair. Throws [ArgumentError] on a missing or
  /// malformed code rather than defaulting to anything — there is no safe
  /// default currency, and picking one would be inventing the value.
  factory Money(double amount, String currencyCode) {
    final code = currencyCode.trim().toUpperCase();
    if (code.length != 3 || !RegExp(r'^[A-Z]{3}$').hasMatch(code)) {
      throw ArgumentError.value(
        currencyCode,
        'currencyCode',
        'must be a 3-letter ISO 4217 code',
      );
    }
    if (amount.isNaN || amount.isInfinite) {
      throw ArgumentError.value(amount, 'amount', 'must be finite');
    }
    return Money._(amount, code);
  }

  /// Parse an amount/currency pair from a backend payload, or return null
  /// when either half is missing or unusable.
  ///
  /// Null rather than a zero-valued [Money]: a caller that gets null has to
  /// decide what to render, and a caller that got `Money(0, 'USD')` would
  /// render a balance of zero. Those are very different claims.
  static Money? tryFrom(Object? amount, Object? currencyCode) {
    if (amount == null || currencyCode is! String) return null;
    final value = amount is num ? amount.toDouble() : double.tryParse('$amount');
    if (value == null) return null;
    try {
      return Money(value, currencyCode);
    } on ArgumentError {
      return null;
    }
  }

  Money operator +(Money other) {
    _assertSameCurrency(other);
    return Money(amount + other.amount, currencyCode);
  }

  Money operator -(Money other) {
    _assertSameCurrency(other);
    return Money(amount - other.amount, currencyCode);
  }

  /// Scale by a plain factor — a percentage of a balance, for instance.
  /// The currency travels with the result.
  Money operator *(double factor) => Money(amount * factor, currencyCode);

  void _assertSameCurrency(Money other) {
    if (other.currencyCode != currencyCode) {
      // Summing across currencies without converting is the failure that
      // looks like a working dashboard right up until it sizes a trade.
      throw StateError(
        'Cannot combine $currencyCode with ${other.currencyCode}; '
        'this type does not convert.',
      );
    }
  }

  /// A display string. Deliberately code-prefixed rather than symbol-based:
  /// '$' is ambiguous across at least a dozen currencies, and this SDK's
  /// whole point is that the denomination is never in doubt.
  String format({int decimals = 2}) =>
      '$currencyCode ${amount.toStringAsFixed(decimals)}';

  @override
  String toString() => format();

  @override
  bool operator ==(Object other) =>
      other is Money &&
      other.amount == amount &&
      other.currencyCode == currencyCode;

  @override
  int get hashCode => Object.hash(amount, currencyCode);
}
