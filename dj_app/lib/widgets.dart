import 'package:flutter/material.dart';

import 'src/api_client.dart';
import 'src/models.dart';

Color statusColor(String status) => switch (status) {
      'pending' => Colors.amber,
      'accepted' => Colors.lightBlueAccent,
      'playing' => Colors.purpleAccent,
      'played' => Colors.greenAccent,
      'rejected' => Colors.redAccent,
      _ => Colors.blueGrey,
    };

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.status, this.dense = false});

  final String status;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final color = statusColor(status);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 8 : 10, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        border: Border.all(color: color.withValues(alpha: 0.7)),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        statusLabel(status),
        style: TextStyle(
          color: color,
          fontSize: dense ? 11 : 12.5,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

void showApiError(BuildContext context, Object error) {
  final message = error is ApiException ? error.message : error.toString();
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: Colors.red.shade700,
      behavior: SnackBarBehavior.floating,
    ),
  );
}

void showInfo(BuildContext context, String message) {
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(message),
      behavior: SnackBarBehavior.floating,
    ),
  );
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, this.subtitle});

  final IconData icon;
  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: style.bodySmall?.color?.withValues(alpha: 0.5)),
            const SizedBox(height: 12),
            Text(title, style: style.titleMedium, textAlign: TextAlign.center),
            if (subtitle != null) ...[
              const SizedBox(height: 6),
              Text(subtitle!,
                  style: style.bodySmall, textAlign: TextAlign.center),
            ],
          ],
        ),
      ),
    );
  }
}

/// Shared list card for a single song request, used by both the listener's
/// "My requests" tab and the DJ dashboard.
class RequestCard extends StatelessWidget {
  const RequestCard({
    super.key,
    required this.item,
    this.canPlay = false,
    this.onPlay,
    this.actions = const [],
  });

  final RequestItem item;
  final bool canPlay;
  final VoidCallback? onPlay;
  final List<Widget> actions;

  String get _title {
    if (item.mixSongTitle.trim().isNotEmpty) return item.mixSongTitle.trim();
    if (item.songs.isNotEmpty) {
      return item.songs.map((s) => s.title ?? s.trackId).join(' + ');
    }
    return 'Mix #${item.id}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final meta = <String>[
      'by ${item.requestedBy}',
      item.mixerType,
      if (item.tipAmount > 0) 'tip \$${item.tipAmount.toStringAsFixed(2)}',
      if (item.restaurantName != null && item.restaurantName!.trim().isNotEmpty)
        item.restaurantName!.trim(),
    ].join('  •  ');

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 8, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 8),
                StatusChip(status: item.status, dense: true),
              ],
            ),
            const SizedBox(height: 4),
            Text(meta, maxLines: 2, overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall),
            if (item.playedAt != null) ...[
              const SizedBox(height: 2),
              Text('Played ${item.playedAt}',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: statusColor('played'))),
            ],
            Row(
              children: [
                IconButton(
                  tooltip: canPlay ? 'Play mix' : 'Mix not ready yet',
                  iconSize: 34,
                  onPressed: canPlay ? onPlay : null,
                  icon: Icon(
                    canPlay
                        ? Icons.play_circle_fill
                        : Icons.hourglass_top_rounded,
                    color: canPlay
                        ? theme.colorScheme.primary
                        : theme.disabledColor,
                  ),
                ),
                const Spacer(),
                ...actions,
              ],
            ),
          ],
        ),
      ),
    );
  }
}
