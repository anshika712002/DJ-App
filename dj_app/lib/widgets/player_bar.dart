import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/player_controller.dart';
import '../theme/app_theme.dart';
import 'artwork.dart';

/// Compact in-app player shown above the bottom navigation. Playback controls
/// and a seek slider replace the old "open in browser / download" behaviour.
class PlayerBar extends StatefulWidget {
  const PlayerBar({super.key});

  @override
  State<PlayerBar> createState() => _PlayerBarState();
}

class _PlayerBarState extends State<PlayerBar> {
  double? _dragValue;

  @override
  Widget build(BuildContext context) {
    final player = context.watch<PlayerController>();
    if (!player.hasTrack) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final durationMs = player.duration.inMilliseconds;
    final hasDuration = durationMs > 0;
    final positionMs = player.position.inMilliseconds.toDouble();
    final maxValue = hasDuration ? durationMs.toDouble() : 1.0;
    final sliderValue = (_dragValue ?? positionMs)
        .clamp(0.0, maxValue)
        .toDouble();

    return Material(
      color: AppColors.surface,
      child: SafeArea(
        top: false,
        child: Container(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: AppColors.outline)),
            gradient: LinearGradient(
              colors: [AppColors.surfaceHigh, AppColors.surface],
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
            ),
          ),
          padding: const EdgeInsets.fromLTRB(12, 8, 8, 4),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Artwork(
                    url: player.artwork,
                    title: player.title,
                    size: 42,
                    isPlaying: player.isPlaying,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          player.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        if ((player.subtitle ?? '').trim().isNotEmpty)
                          Text(
                            player.subtitle!.trim(),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: AppColors.textSecondary,
                            ),
                          ),
                        if (player.error != null)
                          Text(
                            player.error!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: AppColors.danger,
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 4),
                  if (player.isLoading)
                    const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2.4),
                      ),
                    )
                  else
                    IconButton(
                      tooltip: player.isPlaying ? 'Pause' : 'Play',
                      iconSize: 30,
                      color: AppColors.primary,
                      onPressed: player.toggle,
                      icon: Icon(
                        player.isPlaying
                            ? Icons.pause_circle_filled_rounded
                            : Icons.play_circle_fill_rounded,
                      ),
                    ),
                  IconButton(
                    tooltip: 'Close player',
                    icon: const Icon(Icons.close_rounded, size: 20),
                    color: AppColors.textSecondary,
                    onPressed: player.stop,
                  ),
                ],
              ),
              Row(
                children: [
                  SizedBox(
                    width: 38,
                    child: Text(
                      _format(player.position),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                  Expanded(
                    child: SliderTheme(
                      data: SliderTheme.of(context).copyWith(
                        trackHeight: 2.5,
                        thumbShape: const RoundSliderThumbShape(
                          enabledThumbRadius: 6,
                        ),
                        overlayShape: const RoundSliderOverlayShape(
                          overlayRadius: 14,
                        ),
                      ),
                      child: Slider(
                        min: 0,
                        max: maxValue,
                        value: sliderValue,
                        onChanged: hasDuration
                            ? (value) => setState(() => _dragValue = value)
                            : null,
                        onChangeEnd: hasDuration
                            ? (value) {
                                setState(() => _dragValue = null);
                                player.seek(
                                  Duration(milliseconds: value.round()),
                                );
                              }
                            : null,
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 42,
                    child: Text(
                      hasDuration ? _format(player.duration) : '--:--',
                      textAlign: TextAlign.end,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _format(Duration value) {
    final total = value.inSeconds;
    final minutes = total ~/ 60;
    final seconds = total % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }
}
