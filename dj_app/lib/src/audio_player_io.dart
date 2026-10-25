import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'audio_engine.dart';

/// Windows playback without native plugins.
///
/// A tiny hidden PowerShell host owns a WPF `MediaPlayer`. Dart controls it
/// over stdin (play/pause/seek/stop/status) and reads position/duration from
/// stdout. Audio plays directly from the authenticated media URL - nothing is
/// downloaded to disk and no browser window is opened.
class IoAudioEngine extends AudioEngine {
  Process? _process;
  Timer? _poll;
  final List<StreamSubscription<String>> _subscriptions = [];
  bool _commandPending = false;
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

  @override
  Future<void> play(String url) async {
    await _terminate();
    if (!Platform.isWindows) {
      _playing = false;
      _loading = false;
      _error = 'In-app playback is currently supported on Windows and the web.';
      _notify();
      return;
    }

    _playing = true;
    _loading = true;
    _ended = false;
    _position = Duration.zero;
    _duration = Duration.zero;
    _error = null;
    _notify();

    try {
      final process = await Process.start(
        'powershell.exe',
        [
          '-NoProfile',
          '-NonInteractive',
          '-STA',
          '-WindowStyle',
          'Hidden',
          '-EncodedCommand',
          _encodeScript(_hostScript),
        ],
        environment: {...Platform.environment, 'DJ_AUDIO_URL': url},
      );
      _process = process;

      _subscriptions.add(
        process.stdout
            .transform(utf8.decoder)
            .transform(const LineSplitter())
            .listen(_onLine, onError: (_) {}),
      );
      _subscriptions.add(
        process.stderr
            .transform(utf8.decoder)
            .transform(const LineSplitter())
            .listen((_) {}),
      );

      unawaited(
        process.exitCode.then((code) {
          if (!identical(_process, process)) return;
          _process = null;
          _poll?.cancel();
          _poll = null;
          _playing = false;
          _loading = false;
          if (code != 0 && _error == null && !_disposed) {
            _error = 'Playback stopped unexpectedly.';
          }
          _notify();
        }),
      );

      _poll = Timer.periodic(
        const Duration(milliseconds: 500),
        (_) => _requestStatus(),
      );
    } catch (e) {
      _playing = false;
      _loading = false;
      _error = 'Could not start audio playback ($e).';
      _notify();
    }
  }

  @override
  Future<void> resume() async {
    final process = _process;
    if (process == null) return;
    if (_ended) {
      await seek(Duration.zero);
    }
    _playing = true;
    _ended = false;
    _send('play');
    _notify();
  }

  @override
  Future<void> pause() async {
    if (_process == null) return;
    _playing = false;
    _send('pause');
    _notify();
  }

  @override
  Future<void> seek(Duration position) async {
    if (_process == null) return;
    _position = position;
    _ended = false;
    _send('seek:${position.inMilliseconds}');
    _notify();
  }

  @override
  Future<void> stop() async {
    await _terminate();
    _playing = false;
    _loading = false;
    _ended = false;
    _position = Duration.zero;
    _duration = Duration.zero;
    _error = null;
    _notify();
  }

  void _send(String command) {
    final process = _process;
    if (process == null) return;
    try {
      process.stdin.writeln(command);
    } catch (_) {
      // The process exited between the guard and the write.
    }
  }

  void _requestStatus() {
    if (_commandPending) return;
    _commandPending = true;
    _send('status');
  }

  void _onLine(String line) {
    if (line.startsWith('STATUS|')) {
      _commandPending = false;
      final parts = line.split('|');
      if (parts.length < 4) return;
      final positionMs = int.tryParse(parts[1]) ?? 0;
      final durationMs = int.tryParse(parts[2]) ?? 0;
      _position = Duration(milliseconds: positionMs);
      if (durationMs > 0) {
        _duration = Duration(milliseconds: durationMs);
      }
      final state = parts[3];
      _playing = state == 'playing';
      _ended = state == 'ended';
      _loading = false;
      _notify();
      return;
    }
    if (line.startsWith('ERROR|')) {
      _commandPending = false;
      _playing = false;
      _loading = false;
      _error = line.substring('ERROR|'.length).trim();
      if (_error!.isEmpty) {
        _error = 'This track could not be played.';
      }
      _notify();
    }
  }

  Future<void> _terminate() async {
    _poll?.cancel();
    _poll = null;
    _commandPending = false;
    for (final subscription in _subscriptions) {
      await subscription.cancel();
    }
    _subscriptions.clear();
    final process = _process;
    _process = null;
    if (process != null) {
      try {
        process.stdin.writeln('close');
      } catch (_) {}
      try {
        process.kill();
      } catch (_) {}
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(_terminate());
    super.dispose();
  }

  static String _encodeScript(String script) {
    // -EncodedCommand expects UTF-16LE, base64 encoded.
    final bytes = <int>[];
    for (final unit in script.codeUnits) {
      bytes.add(unit & 0xFF);
      bytes.add((unit >> 8) & 0xFF);
    }
    return base64.encode(bytes);
  }
}

const String _hostScript = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Volume = 1.0
$playing = $true
$ended = $false
try {
  $player.Open([Uri]$env:DJ_AUDIO_URL)
  $player.Play()
} catch {
  [Console]::Out.WriteLine('ERROR|' + $_.Exception.Message)
  [Console]::Out.Flush()
  exit 1
}
while ($true) {
  $line = [Console]::In.ReadLine()
  if ($null -eq $line) { break }
  $exit = $false
  try {
    if ($line -eq 'play') {
      if ($ended) { $player.Position = [TimeSpan]::Zero; $ended = $false }
      $player.Play()
      $playing = $true
    } elseif ($line -eq 'pause') {
      $player.Pause()
      $playing = $false
    } elseif ($line -eq 'stop') {
      $player.Stop()
      $playing = $false
    } elseif ($line -eq 'close') {
      $player.Close()
      $exit = $true
    } elseif ($line -match '^seek:(\d+)$') {
      $player.Position = [TimeSpan]::FromMilliseconds([double]$Matches[1])
      $ended = $false
    }
  } catch {
  }
  if ($exit) { break }
  $pos = 0
  $dur = 0
  try { $pos = [int][math]::Floor($player.Position.TotalMilliseconds) } catch {}
  try {
    if ($player.NaturalDuration.HasTimeSpan) {
      $dur = [int][math]::Floor($player.NaturalDuration.TimeSpan.TotalMilliseconds)
    }
  } catch {}
  if ($playing -and $dur -gt 0 -and $pos -ge ($dur - 300)) {
    $playing = $false
    $ended = $true
  }
  $state = 'paused'
  if ($ended) { $state = 'ended' } elseif ($playing) { $state = 'playing' }
  [Console]::Out.WriteLine(('STATUS|{0}|{1}|{2}' -f $pos, $dur, $state))
  [Console]::Out.Flush()
}
''';

AudioEngine createAudioEngine() => IoAudioEngine();

/// Opens a link (for example a YouTube watch page) in the default browser.
Future<void> openExternalUrl(String url) async {
  if (!Platform.isWindows) {
    throw UnsupportedError(
      'Opening external links on ${Platform.operatingSystem} is not supported.',
    );
  }
  final result = await Process.run('rundll32', [
    'url.dll,FileProtocolHandler',
    url,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException(
      'rundll32',
      ['url.dll,FileProtocolHandler', url],
      result.stderr.toString(),
      result.exitCode,
    );
  }
}
