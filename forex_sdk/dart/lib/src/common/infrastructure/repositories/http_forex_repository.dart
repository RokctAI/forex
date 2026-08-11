// Copyright (c) 2026 ROKCT INTELLIGENCE (PTY) LTD
// For license information, please see license.txt

import 'package:base_sdk/base_sdk.dart';
import 'package:flutter/foundation.dart';

import '../../constants/forex_constants.dart';
import '../../domain/interface/forex_repository.dart';
import '../../domain/models/forex_account.dart';
import '../../domain/models/forex_risk.dart';
import '../../domain/models/forex_strategy.dart';

/// Calls the `rforex` backend module over the app's shared Dio client.
///
/// Endpoint paths come from [ForexEndpoints], which mirrors
/// `forex_sdk/frappe/manifest.json`'s whitelisted-method aliases.
///
/// Note where this class does and does not catch. Catalog and risk reads
/// swallow their errors and return the documented safe value; strategy
/// serving and the two writes let theirs propagate. That asymmetry is the
/// contract in [ForexRepository], and it exists because a caller cannot
/// distinguish "locked" from "offline" if both arrive as an empty result.
class HttpForexRepository implements ForexRepository {
  /// Frappe wraps whitelisted return values in a `message` envelope.
  dynamic _unwrap(dynamic data) =>
      data is Map ? (data['message'] ?? data) : data;

  @override
  Future<List<ForexStrategySummary>> listStrategies() async {
    try {
      final client = dioHttp.client(requireAuth: true);
      final response = await client.get(ForexEndpoints.listStrategies);
      final message = _unwrap(response.data);
      if (message is! List) return const [];
      return message
          .whereType<Map>()
          .map((e) =>
              ForexStrategySummary.fromJson(Map<String, dynamic>.from(e)))
          .toList();
    } catch (e) {
      debugPrint('==> HttpForexRepository.listStrategies failure: $e');
      return const [];
    }
  }

  @override
  Future<ForexStrategyDetail> getStrategy(String key) async {
    // Deliberately uncaught: a permission refusal and a dropped connection
    // must reach the caller as different things.
    final client = dioHttp.client(requireAuth: true);
    final response = await client.get(
      ForexEndpoints.getStrategy,
      queryParameters: {'key': key},
    );
    return ForexStrategyDetail.fromJson(
      Map<String, dynamic>.from(_unwrap(response.data) as Map),
    );
  }

  @override
  Future<void> pinVersion(String key, int version) async {
    final client = dioHttp.client(requireAuth: true);
    await client.post(
      ForexEndpoints.pinVersion,
      data: {'key': key, 'version': version},
    );
  }

  @override
  Future<ForexRunVerdict> setActive(String key, {required bool active}) async {
    final client = dioHttp.client(requireAuth: true);
    final response = await client.post(
      ForexEndpoints.setActive,
      data: {'key': key, 'active': active},
    );
    final message = _unwrap(response.data);
    if (message is! Map) {
      // A write that returned an unreadable body is not a success we can
      // report. Fail rather than assume.
      throw StateError('set_active returned an unreadable response');
    }
    return ForexRunVerdict.parse(message['run_verdict']);
  }

  @override
  Future<ForexDashboard> dashboard() async {
    try {
      final client = dioHttp.client(requireAuth: true);
      final response = await client.get(ForexEndpoints.dashboard);
      final message = _unwrap(response.data);
      if (message is! Map) return ForexDashboard.unavailable;
      return ForexDashboard.fromJson(Map<String, dynamic>.from(message));
    } catch (e) {
      // Today this is the expected path: the backend's account connector
      // raises NotImplementedError rather than fabricating balances. The
      // fallback carries no numbers — see ForexDashboard.unavailable.
      debugPrint('==> HttpForexRepository.dashboard failure: $e');
      return ForexDashboard.unavailable;
    }
  }

  @override
  Future<ForexRiskParameters> myRiskParameters() async {
    try {
      final client = dioHttp.client(requireAuth: true);
      final response = await client.get(ForexEndpoints.myRiskProfile);
      return _parseRiskProfile(_unwrap(response.data));
    } catch (e) {
      debugPrint('==> HttpForexRepository.myRiskParameters failure: $e');
      // Absence resolves to the tightest setting, never to unrestricted.
      return ForexRiskParameters.mostConservative;
    }
  }

  @override
  Future<ForexRiskParameters> setRiskPreset(String presetName) async {
    // Uncaught on purpose: a risk change the user believes happened but did
    // not is the wrong thing to be quiet about.
    final client = dioHttp.client(requireAuth: true);
    final response = await client.post(
      ForexEndpoints.setRiskPreset,
      data: {'preset': presetName},
    );
    return _parseRiskProfile(_unwrap(response.data));
  }

  ForexRiskParameters _parseRiskProfile(dynamic message) {
    if (message is! Map) return ForexRiskParameters.mostConservative;
    final profile = message['risk_profile'];
    return ForexRiskParameters.fromJson(
      profile is Map ? Map<String, dynamic>.from(profile) : null,
    );
  }
}
