import 'dart:js_interop';

import 'package:web/web.dart' as web;

/// In-page playback using a single HTML audio element: starting a new track
/// automatically replaces the current one.
web.HTMLAudioElement? _element;

bool get isPlaying => _element?.paused == false;

Future<void> playUrl(String url) async {
  final element = _element ??= web.HTMLAudioElement();
  element.src = url;
  await element.play().toDart;
}

void stopAudio() {
  final element = _element;
  if (element == null) return;
  element.pause();
  element.src = '';
}
