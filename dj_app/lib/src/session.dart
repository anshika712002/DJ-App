import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'models.dart';
import 'token_store.dart';

/// Holds the signed-in user, drives login/signup/refresh and persists the
/// session through the platform-appropriate [TokenStore].
class Session extends ChangeNotifier {
  Session({ApiClient? api, TokenStore? store})
      : api = api ?? ApiClient(),
        _store = store ?? TokenStore() {
    this.api.onRefresh = _refresh;
  }

  final ApiClient api;
  final TokenStore _store;

  AuthSession? _session;
  bool _ready = false;

  AuthSession? get current => _session;
  bool get isReady => _ready;
  bool get isAuthenticated => _session != null;
  bool get isDj => _session?.userRole == UserRole.dj;
  String get userName => _session?.userName ?? '';
  String? get role => _session?.role;

  Future<void> restore() async {
    try {
      final stored = await _store.load();
      if (stored != null &&
          stored['accessToken'] is String &&
          (stored['accessToken'] as String).isNotEmpty) {
        _session = AuthSession.fromJson(stored);
        _applyTokens();
      }
    } catch (_) {
      _session = null;
    } finally {
      _ready = true;
      notifyListeners();
    }
  }

  Future<void> signUp({
    required String userName,
    String? email,
    required String password,
    required String phone,
    required String role,
    String? restaurantName,
  }) async {
    final raw = await api.post('/auth/signup', body: {
      'userName': userName,
      if (email != null && email.isNotEmpty) 'email': email,
      'password': password,
      'phone': phone,
      'role': role,
      if (restaurantName != null && restaurantName.isNotEmpty)
        'restaurantName': restaurantName,
    }, auth: false);
    final response = ApiResponse.fromJson(_asMap(raw));
    if (!response.isSuccess) {
      throw ApiException(
          response.statusCode ?? 400, response.status ?? 'Signup failed');
    }
  }

  Future<void> login({
    required String identifier,
    required String password,
    required String role,
  }) async {
    final raw = await api.post('/auth/login', body: {
      'identifier': identifier,
      'password': password,
      'role': role,
    }, auth: false);
    final response = ApiResponse.fromJson(_asMap(raw));
    if (!response.isSuccess || response.data is! Map) {
      throw ApiException(
          response.statusCode ?? 400, response.status ?? 'Login failed');
    }
    _session = AuthSession.fromJson(response.data as Map<String, dynamic>);
    _applyTokens();
    await _store.save(_session!.toJson());
    notifyListeners();
  }

  Future<void> logout() async {
    _session = null;
    api.accessToken = null;
    api.refreshToken = null;
    await _store.clear();
    notifyListeners();
  }

  Future<bool> _refresh(String currentRefresh) async {
    if (currentRefresh.isEmpty) return false;
    try {
      final raw = await api.post(
        '/auth/refresh',
        body: {'refresh_token': currentRefresh},
        auth: false,
      );
      final response = ApiResponse.fromJson(_asMap(raw));
      final data = response.data;
      if (!response.isSuccess || data is! Map) return false;
      final access = data['accessToken'] as String?;
      final refresh = data['refreshToken'] as String?;
      if (access == null) return false;
      _session = _session?.copyWith(accessToken: access, refreshToken: refresh);
      _applyTokens();
      if (_session != null) await _store.save(_session!.toJson());
      notifyListeners();
      return true;
    } catch (_) {
      return false;
    }
  }

  void _applyTokens() {
    api.setTokens(
      access: _session?.accessToken ?? '',
      refresh: _session?.refreshToken ?? '',
    );
  }

  static Map<String, dynamic> _asMap(dynamic value) =>
      value is Map<String, dynamic> ? value : <String, dynamic>{};
}
