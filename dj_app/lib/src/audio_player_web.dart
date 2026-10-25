import 'dart:js_interop';

import 'package:web/web.dart' as web;

import 'audio_engine.dart';

/// In-page playback using a single HTML audio element. Starting a new track
/// replaces the current one; no new tab or download is triggered.
class WebAudioEngine extends AudioEngine {
  web.HTMLAudioElement? _element;
  bool _disposed = false;

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

  web.HTMLAudioElement _ensureElement() {
    final existing = _element;
    if (existing != null) return existing;

    final element = web.HTMLAudioElement();
    element.preload = 'auto';

    element.addEventListener(
      'timeupdate',
      ((web.Event _) {
        _position = Duration(
          milliseconds: (element.currentTime * 1000).round(),
        );
        _updateDuration(element);
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'loadedmetadata',
      ((web.Event _) {
        _updateDuration(element);
        _loading = false;
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'durationchange',
      ((web.Event _) {
        _updateDuration(element);
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'play',
      ((web.Event _) {
        _playing = true;
        _ended = false;
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'pause',
      ((web.Event _) {
        _playing = false;
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'ended',
      ((web.Event _) {
        _playing = false;
        _ended = true;
        _position = _duration;
        _notify();
      }).toJS,
    );
    element.addEventListener(
      'error',
      ((web.Event _) {
        _playing = false;
        _loading = false;
        _error = 'This track could not be played.';
        _notify();
      }).toJS,
    );

    _element = element;
    return element;
  }

  void _updateDuration(web.HTMLAudioElement element) {
    final value = element.duration;
    if (value.isFinite && value > 0) {
      _duration = Duration(milliseconds: (value * 1000).round());
    }
  }

  @override
  Future<void> play(String url) async {
    final element = _ensureElement();
    _playing = false;
    _loading = true;
    _ended = false;
    _position = Duration.zero;
    _duration = Duration.zero;
    _error = null;
    _notify();

    try {
      element.src = url;
      element.load();
      await element.play().toDart;
      _playing = true;
    } catch (_) {
      _playing = false;
      _error = 'This track could not be played.';
    } finally {
      _loading = false;
      _notify();
    }
  }

  @override
  Future<void> resume() async {
    final element = _element;
    if (element == null) return;
    if (_ended) {
      element.currentTime = 0;
      _position = Duration.zero;
      _ended = false;
    }
    try {
      await element.play().toDart;
      _playing = true;
      _error = null;
    } catch (_) {
      _error = 'This track could not be played.';
    }
    _notify();
  }

  @override
  Future<void> pause() async {
    _element?.pause();
    _playing = false;
    _notify();
  }

  @override
  Future<void> seek(Duration position) async {
    final element = _element;
    if (element == null) return;
    element.currentTime = position.inMilliseconds / 1000;
    _position = position;
    _ended = false;
    _notify();
  }

  @override
  Future<void> stop() async {
    final element = _element;
    if (element != null) {
      element.pause();
      element.removeAttribute('src');
      element.load();
    }
    _playing = false;
    _loading = false;
    _ended = false;
    _position = Duration.zero;
    _duration = Duration.zero;
    _error = null;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _element?.pause();
    super.dispose();
  }
}

AudioEngine createAudioEngine() => WebAudioEngine();

Future<void> openExternalUrl(String url) async {
  web.window.open(url, '_blank');
}
