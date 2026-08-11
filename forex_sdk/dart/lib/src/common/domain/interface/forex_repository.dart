// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

import '../models/forex_account.dart';
import '../models/forex_risk.dart';
import '../models/forex_strategy.dart';

/// The rforex backend, as this SDK's screens use it.
///
/// Unlike the four interfaces alongside it, this one is NOT a cross-SDK
/// seam — rforex is forex_sdk's own backend. It is an interface anyway so
/// that screens can be driven by a fake in a widget test without a live
/// site, and so the HTTP implementation is replaceable.
///
/// **Failure contracts, stated per method rather than assumed.** They are
/// not uniform, and the difference is deliberate: reads that feed a
/// *display* degrade to an empty or unknown value, while reads that feed a
/// *decision about money* propagate their failure. A catalog that fails to
/// an empty list costs the user a refresh. A dashboard that fails to zeroes
/// costs them a position size.
abstract class ForexRepository {
  /// The strategy catalog. Returns an empty list on failure — the screen
  /// shows "couldn't load", not an error dialog.
  Future<List<ForexStrategySummary>> listStrategies();

  /// One strategy with the spec, when entitled.
  ///
  /// **Throws** on failure, including on a permission refusal. The caller
  /// must distinguish "locked" from "offline" and cannot do that against a
  /// null.
  Future<ForexStrategyDetail> getStrategy(String key);

  /// Pin a version. Throws on failure — a pin that silently did not happen
  /// would leave the user believing their bot is on a version it is not.
  Future<void> pinVersion(String key, int version);

  /// Start or pause. Returns the verdict the server applied, which may not
  /// be `run` even when starting — a blocked version overrides the switch.
  /// Throws on failure, for the same reason as [pinVersion].
  Future<ForexRunVerdict> setActive(String key, {required bool active});

  /// The account dashboard.
  ///
  /// Returns [ForexDashboard.unavailable] when the call fails — a value
  /// that carries NO numbers, rather than zeroed ones. The account
  /// connector is not implemented on the backend today, so this is
  /// currently the normal outcome, and it is meant to be visible.
  Future<ForexDashboard> dashboard();

  /// The user's stored risk parameters.
  ///
  /// Returns [ForexRiskParameters.mostConservative] on failure. This is the
  /// one place a fallback value is right: absence of a risk profile must
  /// resolve to the tightest setting, never to unrestricted, and that is
  /// true of a failed read as much as of a missing row.
  Future<ForexRiskParameters> myRiskParameters();

  /// Resolve a preset name to parameters server-side and store them.
  ///
  /// Returns the parameters that were actually stored, which the caller
  /// must then display — not the ones it predicted locally. The client's
  /// copy of the preset table exists so a slider can show a consequence
  /// without a round-trip per drag; the server's copy is the authority, and
  /// on save the two are reconciled in the server's favour.
  ///
  /// Throws on failure: a risk change the user believes happened but did
  /// not is exactly the wrong thing to be quiet about.
  Future<ForexRiskParameters> setRiskPreset(String presetName);
}
