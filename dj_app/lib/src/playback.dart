import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../widgets/feedback.dart';
import 'audio_player.dart';
import 'models.dart';
import 'player_controller.dart';
import 'song_api.dart';

/// Plays a search result. YouTube tracks open on YouTube (the provider only
/// exposes a watch URL); local/licensed tracks preview inside the app through
/// the authenticated media endpoint.
Future<void> playTrack(BuildContext context, SongApi api, Song song) async {
  try {
    if (song.sourceType != 'youtube') {
      await api.ensurePlaybackSession();
      if (!context.mounted) return;
    }
    final url = api.playbackUrl(song);
    if (url == null) {
      showInfo(context, 'This track is not available for playback.');
      return;
    }
    if (song.sourceType == 'youtube') {
      await openExternalUrl(url);
      return;
    }
    await context.read<PlayerController>().playUrl(
      url,
      title: song.title?.trim().isNotEmpty == true
          ? song.title!.trim()
          : song.trackId,
      subtitle: song.artist,
      artwork: song.artwork,
    );
  } catch (e) {
    if (context.mounted) showApiError(context, e);
  }
}

/// Plays a prepared mix from a request. The mix streams inside the app player -
/// no browser tab and no file download.
Future<void> playMix(
  BuildContext context,
  SongApi api,
  RequestItem item,
) async {
  try {
    await api.ensurePlaybackSession();
    if (!context.mounted) return;
    final url = api.audioUrl(item);
    if (url == null) {
      showInfo(
        context,
        'The mix is still being prepared - check back shortly.',
      );
      return;
    }
    final title = item.mixSongTitle.trim().isNotEmpty
        ? item.mixSongTitle.trim()
        : 'Mix #${item.id}';
    final subtitle = item.songs
        .map(
          (song) => song.title?.trim().isNotEmpty == true
              ? song.title!.trim()
              : song.trackId,
        )
        .join(' + ');
    await context.read<PlayerController>().playUrl(
      url,
      title: title,
      subtitle: subtitle.isEmpty ? item.mixerType : subtitle,
      artwork: item.songs.isNotEmpty ? item.songs.first.artwork : null,
    );
  } catch (e) {
    if (context.mounted) showApiError(context, e);
  }
}
