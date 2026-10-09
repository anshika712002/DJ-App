/// Fallback used in tests: nothing plays, calls succeed silently.
bool get isPlaying => false;

Future<void> playUrl(String url) async {}

Future<void> openExternalUrl(String url) async {}

void stopAudio() {}
