// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

/// Endpoint aliases for the `rforex` backend module.
///
/// These mirror `forex_sdk/frappe/manifest.json`'s whitelisted-method
/// aliases exactly. The manifest maps `{app_name}.api.forex.<verb>` onto
/// `{app_name}.rforex.rforex.api.<file>.<func>`; the app name is resolved at
/// composition time, and the host app that composes this SDK is `paas` —
/// same as every other SDK in the estate.
class ForexEndpoints {
  const ForexEndpoints._();

  static const String base = '/api/method/paas.api.forex';

  static const String listStrategies = '$base.list_strategies';
  static const String getStrategy = '$base.get_strategy';
  static const String pinVersion = '$base.pin_version';
  static const String setActive = '$base.set_active';

  static const String dashboard = '$base.dashboard';
  static const String history = '$base.history';
  static const String marginThresholds = '$base.margin_thresholds';

  static const String myRiskProfile = '$base.my_risk_profile';
  static const String availablePresets = '$base.available_presets';
  static const String setRiskPreset = '$base.set_risk_preset';

  static const String credentialStatus = '$base.credential_status';
  static const String storeCredentials = '$base.store_credentials';
  static const String refreshCredentials = '$base.refresh_credentials';
  static const String revokeCredentials = '$base.revoke_credentials';

  static const String myEntitlements = '$base.my_entitlements';
}

/// Route paths this SDK contributes, kept next to the manifest that
/// declares them so the two cannot drift.
class ForexRoutes {
  const ForexRoutes._();

  /// The landing route. `manifest.json`'s `app_routes` entry overrides
  /// `replaceMainRoute` to this, because forex_sdk is the home SDK of its
  /// composition.
  static const String strategies = '/forex-strategies';
  static const String riskPreset = '/forex-risk';
  static const String account = '/forex-account';
}
