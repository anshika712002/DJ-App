/// Fallback used by tests and unsupported platforms: keeps the session in memory.
class TokenStore {
  Map<String, dynamic>? _session;

  Future<void> save(Map<String, dynamic> session) async => _session = session;

  Future<Map<String, dynamic>?> load() async => _session;

  Future<void> clear() async => _session = null;
}
