import 'package:flutter/foundation.dart';

/// Platform-independent playback contract.
///
/// The concrete engine is chosen at compile time by `audio_player.dart`:
/// a real HTML audio element on the web and a controllable media process on
/// Windows. Both keep playback inside the app instead of handing the URL to a
/// browser or the system downloader.
abstract class AudioEngine extends ChangeNotifier {
  bool get isPlaying;
  bool get isLoading;
  bool get isEnded;
  Duration get position;
  Duration get duration;
  String? get error;

  Future<void> play(String url);
  Future<void> resume();
  Future<void> pause();
  Future<void> seek(Duration position);
  Future<void> stop();
}
