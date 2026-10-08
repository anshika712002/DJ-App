import 'dart:convert';
import 'dart:io';

/// Persists the session in a small JSON file under the user's config dir.
/// If that location is not writable (some sandboxed environments) it quietly
/// degrades to in-memory storage so login still works.
class TokenStore {
  File? _file;
  Map<String, dynamic>? _memory;

  File? _resolveFile() {
    if (_file != null) return _file;
    final env = Platform.environment;
    String? dir;
    if (Platform.isWindows && env['APPDATA'] != null) {
      dir = env['APPDATA'];
    } else if (env['HOME'] != null) {
      dir = env['HOME'];
    }
    if (dir == null) return null;
    try {
      final folder = Directory('$dir${Platform.pathSeparator}.dj_app');
      if (!folder.existsSync()) folder.createSync(recursive: true);
      _file = File(
          '$dir${Platform.pathSeparator}.dj_app${Platform.pathSeparator}session.json');
      return _file;
    } catch (_) {
      return null;
    }
  }

  Future<void> save(Map<String, dynamic> session) async {
    _memory = session;
    final file = _resolveFile();
    if (file == null) return;
    try {
      await file.writeAsString(jsonEncode(session), flush: true);
    } catch (_) {
      // Unwritable location -> memory only.
    }
  }

  Future<Map<String, dynamic>?> load() async {
    if (_memory != null) return _memory;
    final file = _resolveFile();
    if (file == null) return null;
    try {
      if (!await file.exists()) return null;
      final raw = jsonDecode(await file.readAsString());
      if (raw is Map<String, dynamic>) {
        _memory = raw;
        return raw;
      }
    } catch (_) {
      // Corrupt file -> treat as logged out.
    }
    return null;
  }

  Future<void> clear() async {
    _memory = null;
    final file = _resolveFile();
    if (file == null) return;
    try {
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }
}
