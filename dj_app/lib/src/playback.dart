import 'package:flutter/material.dart';

import '../widgets/feedback.dart';
import 'audio_player.dart';
import 'models.dart';
import 'song_api.dart';

/// Plays a search result. YouTube tracks open externally (the provider only
/// exposes a watch URL); local/licensed mixes stream through the authenticated
/// media endpoint. Never pretends audio is playing when it is unavailable.
Future<void> playTrack(BuildContext context, SongApi api, Song song) async {
  final url = api.playbackUrl(song);
  if (url == null) {
    showInfo(context, 'This track is not available for playback.');
    return;
  }
  try {
    if (song.sourceType == 'youtube') {
      await openExternalUrl(url);
    } else {
      await playUrl(url);
    }
  } catch (e) {
    if (context.mounted) showApiError(context, e);
  }
}

/// Plays a prepared mix from a request. Only call this when the request is
/// actually playable at the backend (see `isPlayableStatus`).
Future<void> playMix(BuildContext context, SongApi api, RequestItem item) async {
  final url = api.audioUrl(item);
  if (url == null) {
    showInfo(context, 'The mix is still being prepared - check back shortly.');
    return;
  }
  try {
    await playUrl(url);
  } catch (e) {
    if (context.mounted) showApiError(context, e);
  }
}
