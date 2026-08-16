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

/// Whether a strategy card is runnable by this user, and if not, which
/// thing to sell them.
///
/// Three states rather than a bool, because "you're not subscribed" and
/// "you're subscribed but this needs Pro" call for completely different
/// copy — and telling somebody who already pays to "subscribe" is a bug
/// users notice immediately. Mirrors `rforex.entitlements`.
enum ForexEntitlementVerdict {
  allowed,
  needsActive,
  needsUpgrade;

  static ForexEntitlementVerdict parse(Object? raw) {
    switch (raw) {
      case 'allowed':
        return ForexEntitlementVerdict.allowed;
      case 'needs_upgrade':
        return ForexEntitlementVerdict.needsUpgrade;
      default:
        // Fail closed: an unrecognised verdict locks the card. A UI that
        // opened on an unknown string would show an unlocked strategy the
        // server then refuses.
        return ForexEntitlementVerdict.needsActive;
    }
  }

  bool get isAllowed => this == ForexEntitlementVerdict.allowed;
}

/// A version's lifecycle state. Mirrors `rforex.strategy_spec`.
enum ForexVersionStatus {
  draft,
  published,
  retired,
  blocked;

  static ForexVersionStatus parse(Object? raw) {
    switch (raw) {
      case 'published':
        return ForexVersionStatus.published;
      case 'retired':
        return ForexVersionStatus.retired;
      case 'blocked':
        return ForexVersionStatus.blocked;
      default:
        return ForexVersionStatus.draft;
    }
  }
}

/// Why a user's bot is or is not running. Mirrors `rforex.strategy_spec`'s
/// verdict constants.
///
/// [stopBlocked] is the one the whole versioning design exists for: the
/// backend flipped the pinned version to blocked, so the bot stops. It is
/// **not** silently moved onto a newer version — that would change what
/// somebody's money is doing without them asking, at exactly the moment
/// we've decided the thing they chose is unsafe.
enum ForexRunVerdict {
  run,
  stopUnassigned,
  stopBlocked,
  stopNotRunnable,
  stopPaused;

  static ForexRunVerdict parse(Object? raw) {
    switch (raw) {
      case 'run':
        return ForexRunVerdict.run;
      case 'stop_blocked':
        return ForexRunVerdict.stopBlocked;
      case 'stop_not_runnable':
        return ForexRunVerdict.stopNotRunnable;
      case 'stop_paused':
        return ForexRunVerdict.stopPaused;
      default:
        return ForexRunVerdict.stopUnassigned;
    }
  }

  bool get isRunning => this == ForexRunVerdict.run;
}

/// A catalog entry. Carries no spec — the spec is the product and is served
/// only by the gated endpoint.
class ForexStrategySummary {
  final String key;
  final String title;
  final String? summary;
  final String minTier;

  /// The newest published version, or null when the strategy has nothing
  /// publishable yet (drafts only). A null here means it cannot be pinned.
  final int? latestVersion;

  final ForexEntitlementVerdict verdict;

  const ForexStrategySummary({
    required this.key,
    required this.title,
    required this.summary,
    required this.minTier,
    required this.latestVersion,
    required this.verdict,
  });

  bool get isOfferable => latestVersion != null;

  factory ForexStrategySummary.fromJson(Map<String, dynamic> json) {
    return ForexStrategySummary(
      key: '${json['key'] ?? ''}',
      title: '${json['title'] ?? ''}',
      summary: json['summary'] as String?,
      minTier: '${json['min_tier'] ?? 'standard'}',
      latestVersion: json['latest_version'] is num
          ? (json['latest_version'] as num).toInt()
          : null,
      verdict: ForexEntitlementVerdict.parse(json['verdict']),
    );
  }
}

/// A version as it appears in a strategy's version list — status only,
/// never the parameters.
class ForexStrategyVersionSummary {
  final int version;
  final ForexVersionStatus status;
  final bool runnable;
  final String? blockedReason;

  const ForexStrategyVersionSummary({
    required this.version,
    required this.status,
    required this.runnable,
    required this.blockedReason,
  });

  factory ForexStrategyVersionSummary.fromJson(Map<String, dynamic> json) {
    return ForexStrategyVersionSummary(
      version: json['version'] is num ? (json['version'] as num).toInt() : 0,
      status: ForexVersionStatus.parse(json['status']),
      runnable: json['runnable'] == true,
      blockedReason: json['blocked_reason'] as String?,
    );
  }
}

/// A strategy with the spec this user is entitled to, plus their pin.
class ForexStrategyDetail {
  final String key;
  final String title;
  final String? summary;

  /// The version this user runs. Null when they have never pinned one.
  final int? pinnedVersion;

  final ForexRunVerdict runVerdict;

  /// A newer published version exists. An OFFER — nothing moves until the
  /// user accepts it.
  final int? upgradeAvailable;

  /// Set only when [runVerdict] is [ForexRunVerdict.stopBlocked]. Shown to
  /// the user, because a bot that stops without saying why is
  /// indistinguishable from a bot that crashed.
  final String? blockedReason;

  final List<ForexStrategyVersionSummary> versions;

  /// The raw parameter map the bot reads. Null when the caller is not
  /// entitled or the pinned version is blocked.
  final Map<String, dynamic>? spec;

  /// SHA-256 of the canonicalised spec. A running bot can compare it to
  /// what it loaded and refuse to trade if they disagree — immutability you
  /// can check rather than only promise.
  final String? specChecksum;

  const ForexStrategyDetail({
    required this.key,
    required this.title,
    required this.summary,
    required this.pinnedVersion,
    required this.runVerdict,
    required this.upgradeAvailable,
    required this.blockedReason,
    required this.versions,
    required this.spec,
    required this.specChecksum,
  });

  factory ForexStrategyDetail.fromJson(Map<String, dynamic> json) {
    final rawVersions = json['versions'];
    return ForexStrategyDetail(
      key: '${json['key'] ?? ''}',
      title: '${json['title'] ?? ''}',
      summary: json['summary'] as String?,
      pinnedVersion: json['pinned_version'] is num
          ? (json['pinned_version'] as num).toInt()
          : null,
      runVerdict: ForexRunVerdict.parse(json['run_verdict']),
      upgradeAvailable: json['upgrade_available'] is num
          ? (json['upgrade_available'] as num).toInt()
          : null,
      blockedReason: json['blocked_reason'] as String?,
      versions: rawVersions is List
          ? rawVersions
              .whereType<Map>()
              .map((e) => ForexStrategyVersionSummary.fromJson(
                  Map<String, dynamic>.from(e)))
              .toList()
          : const [],
      spec: json['spec'] is Map
          ? Map<String, dynamic>.from(json['spec'] as Map)
          : null,
      specChecksum: json['spec_checksum'] as String?,
    );
  }
}
