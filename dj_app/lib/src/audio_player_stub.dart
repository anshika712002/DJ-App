import 'audio_engine.dart';

/// Fallback used in tests: nothing plays, calls succeed silently.
class StubAudioEngine extends AudioEngine {
  bool _playing = false;
  bool _loading = false;
  bool _ended = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String? _error;

  @override
  bool get isPlaying => _playing;

  @override
  bool get isLoading => _loading;

  @override
  bool get isEnded => _ended;

  @override
  Duration get position => _position;

  @override
  Duration get duration => _duration;

  @override
  String? get error => _error;

  @override
  Future<void> play(String url) async {
    _position = Duration.zero;
    _duration = Duration.zero;
    _ended = false;
    _error = null;
    _playing = true;
    notifyListeners();
  }

  @override
  Future<void> resume() async {
    _playing = true;
    _ended = false;
    notifyListeners();
  }

  @override
  Future<void> pause() async {
    _playing = false;
    notifyListeners();
  }

  @override
  Future<void> seek(Duration position) async {
    _position = position;
    notifyListeners();
  }

  @override
  Future<void> stop() async {
    _playing = false;
    _loading = false;
    _ended = false;
    _position = Duration.zero;
    _duration = Duration.zero;
    notifyListeners();
  }
}

AudioEngine createAudioEngine() => StubAudioEngine();

Future<void> openExternalUrl(String url) async {}
