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
    this.api.onAuthFailure = _handleAuthFailure;
  }

  final ApiClient api;
  final TokenStore _store;

  AuthSession? _session;
  bool _ready = false;

  AuthSession? get current => _session;
  bool get isReady => _ready;
  bool get isAuthenticated => _session != null;
  String get userName => _session?.userName ?? '';

  Future<void> restore() async {
    try {
      final stored = await _store.load();
      if (stored != null &&
          stored['accessToken'] is String &&
          (stored['accessToken'] as String).isNotEmpty) {
        _session = AuthSession.fromJson(stored);
        _applyTokens();

        // Validate/rotate the stored credentials before showing the dashboard.
        // Otherwise an expired access token only fails on the first action and
        // the app appears logged in while every request returns 401.
        if (tokenNeedsRefresh(_session!.accessToken)) {
          final result = await _refresh(_session!.refreshToken);
          if (result == TokenRefreshResult.invalidSession) {
            _session = null;
            api.accessToken = null;
            api.refreshToken = null;
            await _store.clear();
          }
        }
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
  }) async {
    final raw = await api.post(
      '/auth/signup',
      body: {
        'userName': userName,
        if (email != null && email.isNotEmpty) 'email': email,
        'password': password,
        'phone': phone,
      },
      auth: false,
    );
    final response = ApiResponse.fromJson(_asMap(raw));
    if (!response.isSuccess) {
      throw ApiException(
        response.statusCode ?? 400,
        response.status ?? 'Signup failed',
      );
    }
  }

  Future<void> login({
    required String identifier,
    required String password,
  }) async {
    final raw = await api.post(
      '/auth/login',
      body: {'identifier': identifier, 'password': password},
      auth: false,
    );
    final response = ApiResponse.fromJson(_asMap(raw));
    if (!response.isSuccess || response.data is! Map) {
      throw ApiException(
        response.statusCode ?? 400,
        response.status ?? 'Login failed',
      );
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

  Future<TokenRefreshResult> _refresh(String currentRefresh) async {
    if (currentRefresh.isEmpty) return TokenRefreshResult.invalidSession;
    try {
      final raw = await api.post(
        '/auth/refresh',
        body: {'refresh_token': currentRefresh},
        auth: false,
      );
      final response = ApiResponse.fromJson(_asMap(raw));
      final data = response.data;
      if (!response.isSuccess || data is! Map) {
        final code = response.statusCode;
        if (code == 400 || code == 401) {
          return TokenRefreshResult.invalidSession;
        }
        return TokenRefreshResult.unavailable;
      }
      final access = data['accessToken'] as String?;
      final refresh = data['refreshToken'] as String?;
      if (access == null || access.isEmpty) {
        return TokenRefreshResult.invalidSession;
      }
      // A logout may have happened while the refresh was in flight; never
      // resurrect a signed-out session.
      if (_session == null) return TokenRefreshResult.invalidSession;
      _session = _session!.copyWith(accessToken: access, refreshToken: refresh);
      _applyTokens();
      await _store.save(_session!.toJson());
      notifyListeners();
      return TokenRefreshResult.success;
    } on ApiException catch (e) {
      if (e.statusCode == 400 || e.statusCode == 401) {
        return TokenRefreshResult.invalidSession;
      }
      return TokenRefreshResult.unavailable;
    } catch (_) {
      return TokenRefreshResult.unavailable;
    }
  }

  Future<void> _handleAuthFailure() async {
    if (!isAuthenticated) return;
    await logout();
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
