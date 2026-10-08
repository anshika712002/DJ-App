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

/// Thin JSON HTTP wrapper with Bearer auth and one automatic refresh-and-retry
/// on 401. Understands the backend's response envelope loosely: it returns the
/// parsed body and throws [ApiException] for non-2xx responses.
class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  final http.Client _http;

  String? accessToken;
  String? refreshToken;

  /// Supplied by [Session]; returns true when a fresh access token was stored.
  Future<bool> Function(String refreshToken)? onRefresh;

  void setTokens({required String access, required String refresh}) {
    accessToken = access;
    refreshToken = refresh;
  }

  Future<dynamic> get(String path, {Map<String, String>? query, bool auth = true}) =>
      _send('GET', path, query: query, auth: auth);

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

    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (auth && accessToken != null) 'Authorization': 'Bearer $accessToken',
    };

    final http.Response response;
    try {
      switch (method) {
        case 'GET':
          response = await _http.get(uri, headers: headers);
        case 'POST':
          response = await _http.post(uri,
              headers: headers, body: body == null ? null : jsonEncode(body));
        case 'PUT':
          response = await _http.put(uri,
              headers: headers, body: body == null ? null : jsonEncode(body));
        default:
          throw ArgumentError('Unsupported method $method');
      }
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException(0, 'Could not reach the server. Is it running? ($e)');
    }

    final decoded = _tryDecode(response.body);

    if (response.statusCode == 401 && auth && !retried && onRefresh != null) {
      final refreshed = await onRefresh!(refreshToken ?? '');
      if (refreshed) {
        return _send(method, path,
            body: body, query: query, auth: auth, retried: true);
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
