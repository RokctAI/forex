// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

import 'money.dart';

/// Which margin band an account is in. Mirrors `rforex.margin`'s states.
enum ForexMarginState {
  /// No open positions — the margin level is UNDEFINED, not infinite and
  /// not zero. The UI must render the absence rather than a number.
  noPositions,
  healthy,
  warning,
  marginCall,
  stopOut;

  static ForexMarginState parse(Object? raw) {
    switch (raw) {
      case 'healthy':
        return ForexMarginState.healthy;
      case 'warning':
        return ForexMarginState.warning;
      case 'margin_call':
        return ForexMarginState.marginCall;
      case 'stop_out':
        return ForexMarginState.stopOut;
      default:
        return ForexMarginState.noPositions;
    }
  }
}

/// One open position. Every amount carries its own currency — a client
/// rendering a row must not have to reach elsewhere in the payload to know
/// what the number is.
class ForexPosition {
  final String id;
  final String symbol;
  final String side;
  final double volume;
  final Money unrealised;
  final DateTime? openedAt;

  const ForexPosition({
    required this.id,
    required this.symbol,
    required this.side,
    required this.volume,
    required this.unrealised,
    required this.openedAt,
  });

  /// Returns null when the row is unusable — a missing P/L or a missing
  /// currency. **Callers must drop or surface the null, never substitute
  /// zero**: a position silently valued at break-even understates the
  /// account's exposure, which is the direction that hurts.
  static ForexPosition? tryFromJson(Map<String, dynamic> json) {
    final money = Money.tryFrom(json['unrealised_pl'], json['currency']);
    if (money == null) return null;
    final opened = json['opened_at'];
    return ForexPosition(
      id: '${json['id'] ?? ''}',
      symbol: '${json['symbol'] ?? ''}',
      side: '${json['side'] ?? ''}',
      volume: json['volume'] is num ? (json['volume'] as num).toDouble() : 0.0,
      unrealised: money,
      openedAt: opened is String ? DateTime.tryParse(opened) : null,
    );
  }
}

/// A complete, self-consistent reading of the broker account.
///
/// Every field is required. There is no partially-populated snapshot,
/// because a caller cannot tell one from a complete reading — and this is
/// the number a person looks at before deciding how much to risk.
class ForexAccountSnapshot {
  final Money balance;
  final Money equity;
  final Money usedMargin;
  final Money freeMargin;

  /// Null when [usedMargin] is zero. Undefined, not infinite.
  final double? marginLevelPct;

  final ForexMarginState marginState;
  final int openPositionCount;

  /// When the broker said these figures were true. Null means the reading
  /// was untimed, which makes it unpresentable as live.
  final DateTime? asOf;

  /// The server's own judgement of freshness — trusted over a locally
  /// computed age, because the device clock is not trustworthy.
  final bool stale;

  const ForexAccountSnapshot({
    required this.balance,
    required this.equity,
    required this.usedMargin,
    required this.freeMargin,
    required this.marginLevelPct,
    required this.marginState,
    required this.openPositionCount,
    required this.asOf,
    required this.stale,
  });

  /// Parse a `dashboard()` snapshot, or null when any required piece is
  /// missing.
  ///
  /// All-or-nothing on purpose. A snapshot with an equity but no currency,
  /// or a balance but no equity, is not a degraded reading to be shown with
  /// blanks — it is a reading that failed, and the difference matters when
  /// the next thing the user does is choose a position size.
  static ForexAccountSnapshot? tryFromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final currency = json['currency'];
    final balance = Money.tryFrom(json['balance'], currency);
    final equity = Money.tryFrom(json['equity'], currency);
    final used = Money.tryFrom(json['used_margin'], currency);
    final free = Money.tryFrom(json['free_margin'], currency);
    if (balance == null || equity == null || used == null || free == null) {
      return null;
    }
    final level = json['margin_level_pct'];
    final asOf = json['as_of'];
    return ForexAccountSnapshot(
      balance: balance,
      equity: equity,
      usedMargin: used,
      freeMargin: free,
      marginLevelPct: level is num ? level.toDouble() : null,
      marginState: ForexMarginState.parse(json['margin_state']),
      openPositionCount: json['open_position_count'] is num
          ? (json['open_position_count'] as num).toInt()
          : 0,
      asOf: asOf is String ? DateTime.tryParse(asOf) : null,
      // Absent freshness is treated as stale, not fresh.
      stale: json['stale'] != false,
    );
  }
}

/// What the dashboard endpoint returns, including the ordinary "no broker
/// connected" state.
///
/// [snapshot] being null with [connected] true is a real, expected outcome
/// today: the account connector is not implemented, so the backend raises
/// rather than fabricating figures. The UI renders that as an error, which
/// is the correct thing to show.
class ForexDashboard {
  final bool connected;
  final String? reason;
  final String? accountId;
  final ForexAccountSnapshot? snapshot;
  final List<ForexPosition> positions;

  /// Positions the payload contained but that could not be parsed — a
  /// missing currency or P/L. Surfaced rather than swallowed so the UI can
  /// say "3 of 5 positions could not be read" instead of quietly
  /// understating exposure.
  final int unreadablePositionCount;

  const ForexDashboard({
    required this.connected,
    required this.reason,
    required this.accountId,
    required this.snapshot,
    required this.positions,
    required this.unreadablePositionCount,
  });

  factory ForexDashboard.fromJson(Map<String, dynamic> json) {
    final raw = json['positions'];
    final parsed = <ForexPosition>[];
    var unreadable = 0;
    if (raw is List) {
      for (final entry in raw) {
        if (entry is! Map) {
          unreadable++;
          continue;
        }
        final position =
            ForexPosition.tryFromJson(Map<String, dynamic>.from(entry));
        if (position == null) {
          unreadable++;
        } else {
          parsed.add(position);
        }
      }
    }
    return ForexDashboard(
      connected: json['connected'] == true,
      reason: json['reason'] as String?,
      accountId: json['account_id'] as String?,
      snapshot: ForexAccountSnapshot.tryFromJson(
        json['snapshot'] is Map
            ? Map<String, dynamic>.from(json['snapshot'] as Map)
            : null,
      ),
      positions: parsed,
      unreadablePositionCount: unreadable,
    );
  }

  /// The one safe fallback: not connected, nothing known. Used when the
  /// call fails outright — note it carries no numbers at all rather than
  /// zeroed ones.
  static const ForexDashboard unavailable = ForexDashboard(
    connected: false,
    reason: 'unavailable',
    accountId: null,
    snapshot: null,
    positions: [],
    unreadablePositionCount: 0,
  );
}
