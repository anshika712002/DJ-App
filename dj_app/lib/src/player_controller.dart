import 'package:flutter/foundation.dart';

import 'audio_player.dart';

/// App-wide "now playing" state. The widget bar listens to this and the
/// platform engine underneath; playback never leaves the app UI.
class PlayerController extends ChangeNotifier {
  PlayerController({AudioEngine? engine})
    : _engine = engine ?? createAudioEngine() {
    _engine.addListener(_handleEngineChange);
  }

  final AudioEngine _engine;

  bool _hasTrack = false;
  String _title = '';
  String? _subtitle;
  String? _artwork;

  bool get hasTrack => _hasTrack;
  String get title => _title;
  String? get subtitle => _subtitle;
  String? get artwork => _artwork;

  bool get isPlaying => _engine.isPlaying;
  bool get isLoading => _engine.isLoading;
  bool get isEnded => _engine.isEnded;
  Duration get position => _engine.position;
  Duration get duration => _engine.duration;
  String? get error => _engine.error;

  Future<void> playUrl(
    String url, {
    required String title,
    String? subtitle,
    String? artwork,
  }) async {
    _hasTrack = true;
    _title = title;
    _subtitle = subtitle;
    _artwork = artwork;
    notifyListeners();
    await _engine.play(url);
  }

  Future<void> toggle() async {
    if (!_hasTrack) return;
    if (_engine.isPlaying) {
      await _engine.pause();
    } else {
      await _engine.resume();
    }
  }

  Future<void> seek(Duration position) async {
    if (!_hasTrack) return;
    await _engine.seek(position);
  }

  Future<void> stop() async {
    await _engine.stop();
    _hasTrack = false;
    _title = '';
    _subtitle = null;
    _artwork = null;
    notifyListeners();
  }

  void _handleEngineChange() => notifyListeners();

  @override
  void dispose() {
    _engine.removeListener(_handleEngineChange);
    _engine.dispose();
    super.dispose();
  }
}
