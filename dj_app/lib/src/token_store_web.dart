import 'dart:convert';

import 'package:web/web.dart' as web;

/// Persists the session in the browser's localStorage.
class TokenStore {
  static const String _key = 'dj_app.session';

  Future<void> save(Map<String, dynamic> session) async {
    web.window.localStorage.setItem(_key, jsonEncode(session));
  }

  Future<Map<String, dynamic>?> load() async {
    final raw = web.window.localStorage.getItem(_key);
    if (raw == null) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) return decoded;
    } catch (_) {
      // Corrupt entry.
    }
    return null;
  }

  Future<void> clear() async => web.window.localStorage.removeItem(_key);
}
