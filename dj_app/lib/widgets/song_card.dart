import 'package:flutter/material.dart';

import '../src/format.dart';
import '../src/models.dart';
import '../theme/app_theme.dart';
import 'artwork.dart';

/// A single search/track result row. Selection is expressed through the leading
/// checkbox-style toggle; the play action is separate so a tap never
/// accidentally submits a mix.
class SongCard extends StatelessWidget {
  const SongCard({
    super.key,
    required this.song,
    this.selected = false,
    this.selectable = true,
    this.onToggle,
    this.onPlay,
    this.leadingAction,
    this.trailing,
  });

  final Song song;
  final bool selected;
  final bool selectable;
  final VoidCallback? onToggle;
  final VoidCallback? onPlay;
  final Widget? leadingAction;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final meta = <String>[
      if ((song.artist ?? '').trim().isNotEmpty) song.artist!.trim(),
      if (formatDuration(song.duration).isNotEmpty) formatDuration(song.duration),
      sourceLabel(song.sourceType),
      if (song.sourceType != 'youtube' && (song.license ?? '').isNotEmpty)
        song.license!,
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 10, 6, 10),
        child: Row(
          children: [
            if (leadingAction != null) ...[
              leadingAction!,
              const SizedBox(width: 6),
            ],
            InkWell(
              onTap: onToggle,
              borderRadius: AppRadius.borderSm,
              child: Artwork(
                url: song.artwork,
                title: song.title,
                size: 52,
                radius: AppRadius.sm,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    song.title?.trim().isNotEmpty == true
                        ? song.title!.trim()
                        : 'Untitled track',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    meta.join('  •  '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
            if (onPlay != null)
              IconButton(
                tooltip: song.sourceType == 'youtube'
                    ? 'Open on YouTube'
                    : 'Preview audio',
                onPressed: onPlay,
                icon: Icon(
                  song.sourceType == 'youtube'
                      ? Icons.open_in_new_rounded
                      : Icons.play_circle_outline_rounded,
                ),
              ),
            ?trailing,
            if (onToggle != null)
              Padding(
                padding: const EdgeInsets.only(left: 2, right: 4),
                child: IconButton(
                  tooltip: selected ? 'Remove from selection' : 'Add to mix',
                  onPressed: selectable ? onToggle : null,
                  icon: Icon(
                    selected
                        ? Icons.check_circle_rounded
                        : Icons.add_circle_outline_rounded,
                    color: selected
                        ? AppColors.primary
                        : (selectable
                            ? AppColors.textSecondary
                            : AppColors.textMuted),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
