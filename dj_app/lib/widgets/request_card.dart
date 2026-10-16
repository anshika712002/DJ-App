import 'package:flutter/material.dart';

import '../src/models.dart';
import '../theme/app_theme.dart';
import 'artwork.dart';
import 'status_badge.dart';

/// Request card used by the "My Requests" list and home shortcut.
///
/// Playback is gated on the *real* backend lifecycle: a mix is only playable
/// once its status is ready/completed. While the background mix runs the card
/// shows "Processing"; a failed mix shows "Failed".
class RequestCard extends StatelessWidget {
  const RequestCard({
    super.key,
    required this.item,
    this.onPlay,
    this.actions = const [],
    this.showTimeline = true,
  });

  final RequestItem item;
  final VoidCallback? onPlay;
  final List<Widget> actions;
  final bool showTimeline;

  bool get _playable =>
      item.mixedAudioUrl != null && isPlayableStatus(item.status);

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
    final visual = statusVisual(item.status);

    final meta = <String>[
      item.mixerType,
      if (item.requestedAt.trim().isNotEmpty) item.requestedAt,
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 10, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _StackedArtwork(songs: item.songs, isActive: item.status == 'playing'),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        meta.join('  •  '),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: AppColors.textSecondary),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                StatusBadge(status: item.status, dense: true),
              ],
            ),
            if (showTimeline) ...[
              const SizedBox(height: 12),
              _StatusTimeline(status: item.status, color: visual.color),
            ],
            if (item.playedAt != null && item.playedAt!.trim().isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Played at ${item.playedAt}',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: AppColors.success)),
            ],
            const SizedBox(height: 6),
            Row(
              children: [
                Tooltip(
                  message: _playable
                      ? 'Play mix'
                      : (item.mixedAudioUrl == null
                          ? 'The mix is still being prepared'
                          : 'This mix could not be prepared'),
                  child: _playable
                      ? FilledButton.tonalIcon(
                          onPressed: onPlay,
                          icon: const Icon(Icons.play_arrow_rounded),
                          label: const Text('Play mix'),
                        )
                      : OutlinedButton.icon(
                          onPressed: null,
                          icon: const Icon(Icons.lock_clock, size: 18),
                          label: Text(_notPlayableLabel),
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

  String get _notPlayableLabel {
    if (item.mixedAudioUrl == null) {
      if (item.status == 'failed' || item.status == 'rejected') {
        return 'Failed';
      }
      return 'Processing';
    }
    if (item.status == 'failed' || item.status == 'rejected') return 'Failed';
    return 'Unavailable';
  }
}

class _StackedArtwork extends StatelessWidget {
  const _StackedArtwork({required this.songs, required this.isActive});

  final List<Song> songs;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    if (songs.isEmpty) {
      return Artwork(size: 52, title: '?', isPlaying: isActive);
    }
    if (songs.length == 1) {
      return Artwork(
        url: songs.first.artwork,
        title: songs.first.title,
        size: 52,
        isPlaying: isActive,
      );
    }
    return SizedBox(
      width: 52,
      height: 52,
      child: Stack(
        children: [
          Positioned(
            left: 6,
            top: 6,
            child: Artwork(
              url: songs[1].artwork,
              title: songs[1].title,
              size: 40,
              isPlaying: isActive,
            ),
          ),
          Positioned(
            left: 0,
            top: 0,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: AppRadius.borderSm,
                border: Border.all(color: AppColors.background, width: 2),
              ),
              child: Artwork(
                url: songs.first.artwork,
                title: songs.first.title,
                size: 40,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Compact 3-step progress line: Submitted → Mixing → Ready.
class _StatusTimeline extends StatelessWidget {
  const _StatusTimeline({required this.status, required this.color});

  final String status;
  final Color color;

  static const _steps = ['Submitted', 'Mixing', 'Ready'];

  int get _activeIndex {
    switch (status) {
      case 'pending':
        return 1;
      case 'accepted':
      case 'playing':
        return 1;
      case 'ready':
      case 'completed':
      case 'played':
        return 2;
      default:
        return -1;
    }
  }

  @override
  Widget build(BuildContext context) {
    final terminalFailure = status == 'rejected' || status == 'failed';
    if (terminalFailure) {
      return Row(
        children: [
          Icon(Icons.block, size: 14, color: color),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              statusVisual(status).description,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: color),
            ),
          ),
        ],
      );
    }

    final active = _activeIndex;
    return Row(
      children: List.generate(_steps.length, (i) {
        final reached = i <= active;
        return Expanded(
          child: Column(
            children: [
              Row(
                children: [
                  if (i > 0)
                    Expanded(
                      child: Container(
                        height: 2,
                        color: reached ? color : AppColors.outline,
                      ),
                    ),
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: reached ? color : AppColors.surfaceHighest,
                      border: Border.all(
                        color: reached ? color : AppColors.outline,
                      ),
                    ),
                  ),
                  if (i < _steps.length - 1)
                    Expanded(
                      child: Container(
                        height: 2,
                        color: i < active ? color : AppColors.outline,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                _steps[i],
                style: TextStyle(
                  fontSize: 10,
                  color: reached ? AppColors.textSecondary : AppColors.textMuted,
                  fontWeight: reached ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ],
          ),
        );
      }),
    );
  }
}
