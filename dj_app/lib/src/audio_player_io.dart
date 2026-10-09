import 'dart:io';

/// Desktop playback without native plugins: hand the URL to the operating
/// system's default handler (browser / media player) via `rundll32`, which
/// takes the URL as plain arguments and does no shell parsing.
bool _playing = false;

bool get isPlaying => _playing;

Future<void> playUrl(String url) async {
  if (!Platform.isWindows) {
    throw UnsupportedError(
        'On-device playback on ${Platform.operatingSystem} needs a native plugin; '
        'the audio URL can still be opened in a browser.');
  }
  final result = await Process.run('rundll32', [
    'url.dll,FileProtocolHandler',
    url,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException('rundll32', ['url.dll,FileProtocolHandler', url],
        result.stderr.toString(), result.exitCode);
  }
  _playing = true;
}

Future<void> openExternalUrl(String url) async {
  if (!Platform.isWindows) {
    throw UnsupportedError(
        'Opening external links on ${Platform.operatingSystem} is not supported.');
  }
  final result = await Process.run('rundll32', [
    'url.dll,FileProtocolHandler',
    url,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException('rundll32', ['url.dll,FileProtocolHandler', url],
        result.stderr.toString(), result.exitCode);
  }
}

/// The external player is not under our control, so this only resets the flag.
void stopAudio() => _playing = false;
