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
import '../../domain/models/forex_strategy.dart';

/// The strategy catalog — forex_sdk's landing screen.
///
/// Minimal on purpose: enough to show the shape the real screen takes, not
/// a finished design. What it does establish, because these are decisions
/// rather than styling:
///
/// - **Locked cards still show what the strategy is.** Browsing is free;
///   the spec is the product. A card the user cannot run still tells them
///   what it does and what it would take to unlock it.
/// - **The two locked states say different things.** "Subscribe" and
///   "upgrade to Pro" are different sentences, and showing the first to
///   somebody who already pays is the mistake the three-state verdict
///   exists to prevent.
/// - **A blocked strategy is called out, not hidden.** If the backend has
///   stopped a version, the user is told, because a bot that stops
///   silently is indistinguishable from a bot that crashed.
class ForexStrategyListPage extends StatefulWidget {
  /// Injectable for tests; defaults to the wired repository.
  final ForexRepository? repository;

  /// Called when a card is tapped. Supplied by the host route, because
  /// navigation targets are the app's business, not this SDK's.
  final void Function(ForexStrategySummary strategy)? onOpen;

  /// Called when a locked card's unlock action is tapped.
  final void Function(ForexStrategySummary strategy)? onUnlock;

  const ForexStrategyListPage({
    super.key,
    this.repository,
    this.onOpen,
    this.onUnlock,
  });

  @override
  State<ForexStrategyListPage> createState() => _ForexStrategyListPageState();
}

class _ForexStrategyListPageState extends State<ForexStrategyListPage> {
  late final ForexRepository _repository;
  Future<List<ForexStrategySummary>>? _future;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? ForexDependencies.repository();
    _future = _repository.listStrategies();
  }

  Future<void> _refresh() async {
    setState(() => _future = _repository.listStrategies());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Strategies')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: FutureBuilder<List<ForexStrategySummary>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            final strategies = snapshot.data ?? const <ForexStrategySummary>[];
            if (strategies.isEmpty) {
              // listStrategies() returns an empty list on failure as well as
              // on an empty catalog, so this copy has to cover both without
              // claiming which. "Nothing here" plus a pull-to-refresh is
              // honest about the ambiguity; "no strategies published" would
              // not be.
              return ListView(
                children: const [
                  SizedBox(height: 120),
                  Center(child: Text('Nothing to show yet. Pull to refresh.')),
                ],
              );
            }
            return ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: strategies.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) => _StrategyCard(
                strategy: strategies[index],
                onOpen: widget.onOpen,
                onUnlock: widget.onUnlock,
              ),
            );
          },
        ),
      ),
    );
  }
}

class _StrategyCard extends StatelessWidget {
  final ForexStrategySummary strategy;
  final void Function(ForexStrategySummary)? onOpen;
  final void Function(ForexStrategySummary)? onUnlock;

  const _StrategyCard({
    required this.strategy,
    required this.onOpen,
    required this.onUnlock,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final unlocked = strategy.verdict.isAllowed;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: unlocked && strategy.isOfferable
            ? () => onOpen?.call(strategy)
            : null,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      strategy.title,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  if (!unlocked)
                    Icon(Icons.lock_outline,
                        size: 18, color: theme.disabledColor),
                ],
              ),
              if (strategy.summary != null) ...[
                const SizedBox(height: 6),
                // Shown even when locked: browsing is free, and a paywall
                // nobody can see the inside of does not sell anything.
                Text(strategy.summary!, style: theme.textTheme.bodySmall),
              ],
              const SizedBox(height: 12),
              if (!strategy.isOfferable)
                // No published version. Distinct from locked — this one is
                // not for sale yet, and offering to unlock it would be a
                // dead end.
                Text(
                  'Not available yet.',
                  style: theme.textTheme.labelMedium
                      ?.copyWith(color: theme.disabledColor),
                )
              else
                _CardFooter(strategy: strategy, onUnlock: onUnlock),
            ],
          ),
        ),
      ),
    );
  }
}

class _CardFooter extends StatelessWidget {
  final ForexStrategySummary strategy;
  final void Function(ForexStrategySummary)? onUnlock;

  const _CardFooter({required this.strategy, required this.onUnlock});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    switch (strategy.verdict) {
      case ForexEntitlementVerdict.allowed:
        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Version ${strategy.latestVersion}',
                style: theme.textTheme.labelMedium),
            const Icon(Icons.chevron_right),
          ],
        );
      case ForexEntitlementVerdict.needsUpgrade:
        // Not "subscribe" — this user already pays.
        return _UnlockRow(
          message: 'Included with ${strategy.minTier}',
          action: 'Upgrade',
          onTap: () => onUnlock?.call(strategy),
        );
      case ForexEntitlementVerdict.needsActive:
        return _UnlockRow(
          message: 'Needs an active subscription',
          action: 'See plans',
          onTap: () => onUnlock?.call(strategy),
        );
    }
  }
}

class _UnlockRow extends StatelessWidget {
  final String message;
  final String action;
  final VoidCallback onTap;

  const _UnlockRow({
    required this.message,
    required this.action,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Flexible(
          child: Text(message, style: Theme.of(context).textTheme.labelMedium),
        ),
        TextButton(onPressed: onTap, child: Text(action)),
      ],
    );
  }
}
