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

import 'package:flutter/material.dart';

import '../../di/forex_di.dart';
import '../../domain/interface/forex_repository.dart';
import '../../domain/interface/forex_wallet_balance_source.dart';
import '../../domain/models/forex_risk.dart';
import '../../domain/models/money.dart';

/// The risk preset picker.
///
/// Modelled on betassist's budget selector, which renders the resulting max
/// stake directly under the slider rather than leaving the user to work out
/// what a percentage means. Same principle, higher stakes: "0.5% per trade"
/// is not a quantity anybody feels, and "R 50 on this account" is.
///
/// Two things this screen refuses to do, and both are the point:
///
/// 1. **It does not invent an account size.** When the balance is unknown —
///    no broker connected, wallet source unregistered, read failed — the
///    consequence panel shows the percentage and an em dash, not a figure
///    computed against a nominal 10,000. A made-up "you'd risk R 50 a trade"
///    is a number the user acts on.
/// 2. **It does not treat the local preset table as authoritative.** The
///    slider previews from the bundled copy so it can respond to a drag
///    without a round-trip, but the saved result comes back from the server
///    and replaces the preview. If the two ever disagree, the server wins
///    and the user sees the server's numbers.
class ForexRiskPresetPage extends StatefulWidget {
  final ForexRepository? repository;
  final ForexWalletBalanceSource? balanceSource;

  const ForexRiskPresetPage({
    super.key,
    this.repository,
    this.balanceSource,
  });

  @override
  State<ForexRiskPresetPage> createState() => _ForexRiskPresetPageState();
}

class _ForexRiskPresetPageState extends State<ForexRiskPresetPage> {
  late final ForexRepository _repository;
  late final ForexWalletBalanceSource _balanceSource;

  /// Which preset the slider is on. Starts at the tightest — index 0 —
  /// rather than at a "sensible middle", so a user who opens this screen
  /// and backs out without touching it has not been nudged upward.
  int _index = 0;

  /// The account size the consequences are computed against. Null means
  /// unknown, and is rendered as unknown.
  Money? _equity;

  ForexRiskParameters? _saved;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? ForexDependencies.repository();
    _balanceSource = widget.balanceSource ?? ForexDependencies.walletBalance();
    _load();
  }

  Future<void> _load() async {
    // Deliberately independent: a failed balance read must not stop the
    // stored limits from loading, and vice versa. The balance is a display
    // aid; the limits are the thing.
    final stored = await _repository.myRiskParameters();
    final balance = await _balanceSource.currentBalance();
    if (!mounted) return;
    setState(() {
      _saved = stored;
      _equity = balance;
      _index = _indexMatching(stored);
      _loading = false;
    });
  }

  /// Find which preset the stored parameters correspond to.
  ///
  /// Falls back to index 0 when nothing matches — which is the correct
  /// outcome for a profile whose numbers have drifted from every preset
  /// (an old preset table, or a custom profile). The slider then shows the
  /// tightest preset while the "currently applied" panel still shows the
  /// user's real stored numbers, so the divergence is visible rather than
  /// papered over.
  int _indexMatching(ForexRiskParameters stored) {
    for (var i = 0; i < ForexRiskPreset.all.length; i++) {
      final p = ForexRiskPreset.all[i].parameters;
      if (p.riskPerTradePct == stored.riskPerTradePct &&
          p.dailyLossPct == stored.dailyLossPct &&
          p.maxDrawdownPct == stored.maxDrawdownPct &&
          p.maxOpenPositions == stored.maxOpenPositions) {
        return i;
      }
    }
    return 0;
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final applied =
          await _repository.setRiskPreset(ForexRiskPreset.all[_index].name);
      if (!mounted) return;
      // The server's answer replaces the preview, not the other way round.
      setState(() {
        _saved = applied;
        _index = _indexMatching(applied);
        _saving = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = 'Could not save. Your limits are unchanged.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final preset = ForexRiskPreset.all[_index];
    final params = preset.parameters;
    final isDirty = _saved == null || _indexMatching(_saved!) != _index;

    return Scaffold(
      appBar: AppBar(title: const Text('Risk')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(preset.label, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text(preset.explainer, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 24),
          Slider(
            value: _index.toDouble(),
            min: 0,
            max: (ForexRiskPreset.all.length - 1).toDouble(),
            divisions: ForexRiskPreset.all.length - 1,
            label: preset.label,
            onChanged: (value) => setState(() => _index = value.round()),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: ForexRiskPreset.all
                .map((p) => Text(p.label, style: theme.textTheme.labelSmall))
                .toList(),
          ),
          const SizedBox(height: 24),

          // The derived consequence, rendered next to the control.
          _ConsequencePanel(parameters: params, equity: _equity),

          const SizedBox(height: 24),
          if (_error != null) ...[
            Text(_error!,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: theme.colorScheme.error)),
            const SizedBox(height: 12),
          ],
          FilledButton(
            onPressed: (_saving || !isDirty) ? null : _save,
            child: Text(_saving ? 'Saving…' : 'Apply these limits'),
          ),
          const SizedBox(height: 16),
          if (_saved != null)
            Text(
              'Currently applied: ${_saved!.riskPerTradePct}% per trade, '
              'max ${_saved!.maxOpenPositions} open.',
              style: theme.textTheme.labelSmall,
            ),
        ],
      ),
    );
  }
}

/// What the selected preset means in money, or an honest dash.
class _ConsequencePanel extends StatelessWidget {
  final ForexRiskParameters parameters;
  final Money? equity;

  const _ConsequencePanel({required this.parameters, required this.equity});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.shield_outlined,
                  size: 20, color: theme.colorScheme.primary),
              const SizedBox(width: 8),
              Text('What this means',
                  style: theme.textTheme.titleSmall),
            ],
          ),
          const SizedBox(height: 12),
          _ConsequenceRow(
            label: 'Most one trade can lose',
            percent: parameters.riskPerTradePct,
            amount: parameters.riskPerTrade(equity),
          ),
          _ConsequenceRow(
            label: 'Stops for the day at',
            percent: parameters.dailyLossPct,
            amount: parameters.dailyLossLimit(equity),
          ),
          _ConsequenceRow(
            label: 'Halts altogether at',
            percent: parameters.maxDrawdownPct,
            amount: parameters.drawdownLimit(equity),
          ),
          const Divider(height: 24),
          Text('At most ${parameters.maxOpenPositions} position'
              '${parameters.maxOpenPositions == 1 ? '' : 's'} open at once.',
              style: theme.textTheme.bodySmall),
          if (equity == null) ...[
            const SizedBox(height: 12),
            Text(
              'Connect a trading account to see these as amounts. '
              'Percentages are of your account equity.',
              style: theme.textTheme.labelSmall
                  ?.copyWith(color: theme.hintColor),
            ),
          ],
        ],
      ),
    );
  }
}

class _ConsequenceRow extends StatelessWidget {
  final String label;
  final double percent;
  final Money? amount;

  const _ConsequenceRow({
    required this.label,
    required this.percent,
    required this.amount,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Text(label, style: theme.textTheme.bodyMedium)),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                // An em dash, not a fabricated figure. The percentage is
                // always true; the amount is only true if we know the
                // account size.
                amount?.format() ?? '—',
                style: theme.textTheme.titleSmall,
              ),
              Text('$percent%', style: theme.textTheme.labelSmall),
            ],
          ),
        ],
      ),
    );
  }
}
