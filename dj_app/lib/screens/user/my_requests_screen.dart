import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../src/models.dart';
import '../../src/my_requests_controller.dart';
import '../../src/playback.dart';
import '../../src/song_api.dart';
import '../../theme/app_theme.dart';
import '../../widgets/feedback.dart';
import '../../widgets/layout.dart';
import '../../widgets/request_card.dart';
import '../../widgets/state_views.dart';
import '../../widgets/status_badge.dart';

/// The user's own requests. Read-only status tracking: mixes are prepared in
/// the background by the backend and become playable once ready.
class MyRequestsScreen extends StatelessWidget {
  const MyRequestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<MyRequestsController>();

    if (controller.loading && controller.items.isEmpty) {
      return const LoadingView(label: 'Loading your requests');
    }
    if (controller.items.isEmpty) {
      if (controller.error != null) {
        return ErrorStateView(
          message: controller.error!,
          onRetry: () => controller.load(),
        );
      }
      return const EmptyStateView(
        icon: Icons.queue_music_rounded,
        title: 'No requests yet',
        subtitle:
            'Search for a song, add it to the mix tray and submit a request. Its progress will show up here.',
      );
    }

    return RefreshIndicator(
      onRefresh: () => controller.load(),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          ConstrainedContent(
            maxWidth: 900,
            child: Column(
              children: [
                for (final item in controller.items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                    child: RequestCard(
                      item: item,
                      onPlay: () => playMix(context, context.read<SongApi>(), item),
                      actions: [
                        if (item.status == 'failed' && item.songs.isNotEmpty)
                          FilledButton.tonalIcon(
                            onPressed: () => _retry(context, item),
                            icon: const Icon(Icons.refresh_rounded, size: 18),
                            label: const Text('Retry'),
                          ),
                        IconButton(
                          tooltip: 'Status details',
                          icon: const Icon(Icons.info_outline_rounded),
                          onPressed: () => _showDetails(context, item),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _retry(BuildContext context, RequestItem item) async {
    final api = context.read<SongApi>();
    final controller = context.read<MyRequestsController>();
    try {
      final id = await api.requestMix(
        tracks: item.songs,
        mixer: item.mixerType,
      );
      if (!context.mounted) return;
      showInfo(context, 'Retrying mix (#$id). Track it here.');
      await controller.load();
    } catch (e) {
      if (!context.mounted) return;
      showApiError(context, e);
    }
  }

  void _showDetails(BuildContext context, RequestItem item) {
    final visual = statusVisual(item.status);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surfaceHigh,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    item.mixSongTitle.isEmpty
                        ? 'Mix #${item.id}'
                        : item.mixSongTitle,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                StatusBadge(status: item.status),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            Text(visual.description, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: AppSpacing.md),
            _DetailRow(label: 'Requested', value: item.requestedAt),
            if (item.playedAt != null)
              _DetailRow(label: 'Played', value: item.playedAt!),
            _DetailRow(label: 'Mixer', value: item.mixerType),
            _DetailRow(
              label: 'Playable',
              value: (isPlayableStatus(item.status) &&
                      item.mixedAudioUrl != null)
                  ? 'Yes'
                  : 'No',
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          SizedBox(
            width: 96,
            child: Text(
              label,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: AppColors.textSecondary),
            ),
          ),
          Expanded(
            child: Text(
              value.isEmpty ? '—' : value,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}
