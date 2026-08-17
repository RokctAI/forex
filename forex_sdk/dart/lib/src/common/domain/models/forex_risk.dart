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

import 'money.dart';

/// The four resolved risk parameters — the complete risk surface a strategy
/// is allowed to see.
///
/// **Presets resolve to these numbers, and these numbers are what is
/// stored.** Storing the preset NAME instead would mean that redefining
/// "balanced" next quarter silently re-risked every account that had ever
/// chosen it, without anybody consenting or noticing. The name survives only
/// as a label ([ForexRiskPreset.name]).
///
/// Mirrors `forex_sdk/frappe/src/rforex/risk_presets.py`. The backend is the
/// authority — it re-resolves and re-clamps on every read, so a client that
/// somehow produced a wider set could not act on it. This copy exists so the
/// picker can show a consequence without a round-trip per drag.
class ForexRiskParameters {
  /// Maximum equity fraction one position may risk between entry and stop.
  final double riskPerTradePct;

  /// Loss within one trading day that stops new entries for the rest of it.
  final double dailyLossPct;

  /// Fall from peak equity that flattens and halts the bot.
  final double maxDrawdownPct;

  /// At least 1.
  final int maxOpenPositions;

  const ForexRiskParameters({
    required this.riskPerTradePct,
    required this.dailyLossPct,
    required this.maxDrawdownPct,
    required this.maxOpenPositions,
  });

  /// The tightest value available for each parameter, derived from
  /// [ForexRiskPreset.all] rather than hardcoded — so adding a tighter
  /// preset moves the floor automatically.
  ///
  /// This is what absence resolves to: a missing profile, an unregistered
  /// adapter, a failed load. **Never unrestricted.**
  static ForexRiskParameters get mostConservative {
    final presets = ForexRiskPreset.all;
    return ForexRiskParameters(
      riskPerTradePct: presets
          .map((p) => p.parameters.riskPerTradePct)
          .reduce((a, b) => a < b ? a : b),
      dailyLossPct: presets
          .map((p) => p.parameters.dailyLossPct)
          .reduce((a, b) => a < b ? a : b),
      maxDrawdownPct: presets
          .map((p) => p.parameters.maxDrawdownPct)
          .reduce((a, b) => a < b ? a : b),
      maxOpenPositions: presets
          .map((p) => p.parameters.maxOpenPositions)
          .reduce((a, b) => a < b ? a : b),
    );
  }

  /// Parse a stored profile. Every field falls back to its
  /// [mostConservative] value independently, so a half-written profile
  /// cannot leave one dimension open.
  factory ForexRiskParameters.fromJson(Map<String, dynamic>? json) {
    final floor = mostConservative;
    if (json == null) return floor;
    double pct(String key, double fallback) {
      final raw = json[key];
      final value = raw is num ? raw.toDouble() : double.tryParse('$raw');
      if (value == null || value.isNaN || value <= 0) return fallback;
      return value;
    }

    final rawPositions = json['max_open_positions'];
    final positions =
        rawPositions is num ? rawPositions.toInt() : int.tryParse('$rawPositions');

    return ForexRiskParameters(
      riskPerTradePct: pct('risk_per_trade_pct', floor.riskPerTradePct),
      dailyLossPct: pct('daily_loss_pct', floor.dailyLossPct),
      maxDrawdownPct: pct('max_drawdown_pct', floor.maxDrawdownPct),
      maxOpenPositions: (positions == null || positions < 1)
          ? floor.maxOpenPositions
          : positions,
    );
  }

  Map<String, dynamic> toJson() => {
        'risk_per_trade_pct': riskPerTradePct,
        'daily_loss_pct': dailyLossPct,
        'max_drawdown_pct': maxDrawdownPct,
        'max_open_positions': maxOpenPositions,
      };

  /// The consequence of these limits on a known account equity — the number
  /// a risk picker shows next to the control.
  ///
  /// Returns null when the equity is unknown. **It does not substitute a
  /// nominal account size**: a made-up 10,000 rendered as "you'd risk 50 a
  /// trade" is a number the user will act on, and it would be fiction.
  Money? riskPerTrade(Money? equity) =>
      equity == null ? null : equity * (riskPerTradePct / 100.0);

  Money? dailyLossLimit(Money? equity) =>
      equity == null ? null : equity * (dailyLossPct / 100.0);

  Money? drawdownLimit(Money? equity) =>
      equity == null ? null : equity * (maxDrawdownPct / 100.0);
}

/// A named preset: a shortcut for picking numbers, not a reference to them.
class ForexRiskPreset {
  final String name;
  final String label;
  final String explainer;
  final ForexRiskParameters parameters;

  const ForexRiskPreset({
    required this.name,
    required this.label,
    required this.explainer,
    required this.parameters,
  });

  /// Kept in sync with `rforex/risk_presets.py`'s PRESETS. These are
  /// defensible starting points, NOT measured values — nothing in this
  /// repository has had market data through it.
  static const List<ForexRiskPreset> all = [
    ForexRiskPreset(
      name: 'conservative',
      label: 'Conservative',
      explainer: 'One position at a time, and the smallest stake per trade.',
      parameters: ForexRiskParameters(
        riskPerTradePct: 0.25,
        dailyLossPct: 1.0,
        maxDrawdownPct: 5.0,
        maxOpenPositions: 1,
      ),
    ),
    ForexRiskPreset(
      name: 'balanced',
      label: 'Balanced',
      explainer: 'Twice the stake, up to two positions open at once.',
      parameters: ForexRiskParameters(
        riskPerTradePct: 0.5,
        dailyLossPct: 2.0,
        maxDrawdownPct: 10.0,
        maxOpenPositions: 2,
      ),
    ),
    ForexRiskPreset(
      name: 'aggressive',
      label: 'Aggressive',
      explainer:
          'Four times the conservative stake. A run of losses reaches the '
          'drawdown halt far sooner.',
      parameters: ForexRiskParameters(
        riskPerTradePct: 1.0,
        dailyLossPct: 4.0,
        maxDrawdownPct: 20.0,
        maxOpenPositions: 4,
      ),
    ),
  ];

  /// Resolve a preset by name. An unknown or null name resolves to the
  /// tightest preset, never to the last one that happened to parse.
  static ForexRiskPreset resolve(String? name) {
    if (name == null) return all.first;
    final key = name.trim().toLowerCase();
    for (final preset in all) {
      if (preset.name == key) return preset;
    }
    return all.first;
  }
}
