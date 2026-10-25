import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;

  const ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

/// Outcome of an attempt to exchange a refresh token for a new access token.
enum TokenRefreshResult {
  /// Fresh tokens were stored and the original request can be retried.
  success,

  /// The refresh token is expired/revoked - the session must be cleared.
  invalidSession,

  /// The refresh endpoint could not be reached; keep the session and retry
  /// later instead of silently signing the user out.
  unavailable,
}

/// Reads the `exp` claim from a JWT without verifying its signature. Used only
/// to decide whether the token should be refreshed before a request/media URL.
DateTime? tokenExpiry(String token) {
  final parts = token.split('.');
  if (parts.length != 3) return null;
  try {
    final payload = jsonDecode(
      utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
    );
    if (payload is! Map) return null;
    final exp = payload['exp'];
    if (exp is! num) return null;
    return DateTime.fromMillisecondsSinceEpoch(exp.toInt() * 1000, isUtc: true);
  } catch (_) {
    return null;
  }
}

bool tokenNeedsRefresh(
  String token, {
  Duration skew = const Duration(minutes: 5),
}) {
  final expiry = tokenExpiry(token);
  if (expiry == null) return true;
  return DateTime.now().toUtc().isAfter(expiry.subtract(skew));
}

/// Thin JSON HTTP wrapper with Bearer auth and one automatic refresh-and-retry
/// on 401. Understands the backend's response envelope loosely: it returns the
/// parsed body and throws [ApiException] for non-2xx responses.
class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  final http.Client _http;

  String? accessToken;
  String? refreshToken;

  /// Supplied by [Session]; exchanges the refresh token for fresh credentials.
  Future<TokenRefreshResult> Function(String refreshToken)? onRefresh;

  /// Supplied by [Session]; called when the refresh token is definitively
  /// invalid so the app can return to the login screen immediately.
  Future<void> Function()? onAuthFailure;

  Future<TokenRefreshResult>? _refreshInFlight;

  void setTokens({required String access, required String refresh}) {
    accessToken = access;
    refreshToken = refresh;
  }

  /// Starts at most one refresh call at a time. Concurrent 401 responses share
  /// the same future, so a single-use/rotating refresh token is never consumed
  /// twice from parallel requests.
  Future<TokenRefreshResult> _refreshAccessToken(String staleAccessToken) {
    final inFlight = _refreshInFlight;
    if (inFlight != null) return inFlight;

    final future = _performRefresh(staleAccessToken);
    _refreshInFlight = future;
    return future.whenComplete(() {
      if (identical(_refreshInFlight, future)) _refreshInFlight = null;
    });
  }

  Future<TokenRefreshResult> _performRefresh(String staleAccessToken) async {
    // Another request may already have installed a fresh access token while
    // this request was in flight. Retry with it instead of rotating again.
    if (accessToken != null && accessToken != staleAccessToken) {
      return TokenRefreshResult.success;
    }
    final refresh = refreshToken;
    final callback = onRefresh;
    if (refresh == null || refresh.isEmpty || callback == null) {
      return TokenRefreshResult.invalidSession;
    }
    try {
      return await callback(refresh);
    } catch (_) {
      return TokenRefreshResult.unavailable;
    }
  }

  /// Makes sure [accessToken] is valid before it is embedded in a media URL
  /// (media players bypass the normal 401 retry flow).
  Future<bool> ensureValidToken({
    Duration skew = const Duration(minutes: 2),
  }) async {
    final token = accessToken;
    if (token == null || token.isEmpty) return false;
    if (!tokenNeedsRefresh(token, skew: skew)) return true;
    final result = await _refreshAccessToken(token);
    if (result == TokenRefreshResult.invalidSession) {
      await onAuthFailure?.call();
    }
    return result == TokenRefreshResult.success;
  }

  Future<dynamic> get(
    String path, {
    Map<String, String>? query,
    bool auth = true,
  }) => _send('GET', path, query: query, auth: auth);

  Future<dynamic> post(String path, {Object? body, bool auth = true}) =>
      _send('POST', path, body: body, auth: auth);

  Future<dynamic> put(String path, {Object? body, bool auth = true}) =>
      _send('PUT', path, body: body, auth: auth);

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool auth = true,
    bool retried = false,
  }) async {
    var uri = Uri.parse(AppConfig.httpUrl(path));
    if (query != null && query.isNotEmpty) {
      uri = uri.replace(queryParameters: {...uri.queryParameters, ...query});
    }

    final tokenUsed = accessToken;
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (auth && tokenUsed != null) 'Authorization': 'Bearer $tokenUsed',
    };

    final http.Response response;
    try {
      switch (method) {
        case 'GET':
          response = await _http.get(uri, headers: headers);
        case 'POST':
          response = await _http.post(
            uri,
            headers: headers,
            body: body == null ? null : jsonEncode(body),
          );
        case 'PUT':
          response = await _http.put(
            uri,
            headers: headers,
            body: body == null ? null : jsonEncode(body),
          );
        default:
          throw ArgumentError('Unsupported method $method');
      }
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException(0, 'Could not reach the server. Is it running? ($e)');
    }

    final decoded = _tryDecode(response.body);

    if (response.statusCode == 401 && auth) {
      if (!retried) {
        final result = await _refreshAccessToken(tokenUsed ?? '');
        if (result == TokenRefreshResult.success) {
          return _send(
            method,
            path,
            body: body,
            query: query,
            auth: auth,
            retried: true,
          );
        }
        if (result == TokenRefreshResult.invalidSession) {
          await onAuthFailure?.call();
        }
      } else {
        // The freshly refreshed token was rejected too: this session is no
        // longer usable, so the app must not stay on the dashboard.
        await onAuthFailure?.call();
      }
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.statusCode, _messageFor(decoded, response));
    }
    return decoded;
  }

  static dynamic _tryDecode(String body) {
    if (body.isEmpty) return null;
    try {
      return jsonDecode(body);
    } catch (_) {
      return null;
    }
  }

  static String _messageFor(dynamic decoded, http.Response response) {
    if (decoded is Map) {
      final detail = decoded['detail'];
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] != null) {
          final loc = first['loc'];
          final field = (loc is List && loc.isNotEmpty) ? loc.last : 'field';
          return '$field: ${first['msg']}';
        }
        return detail.toString();
      }
      if (decoded['status'] is String) return decoded['status'] as String;
    }
    if (response.body.isNotEmpty && response.body.length < 300) {
      return response.body;
    }
    return 'Request failed with status ${response.statusCode}';
  }
}
