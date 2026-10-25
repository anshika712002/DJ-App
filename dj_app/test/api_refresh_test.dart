import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:dj_app/src/api_client.dart';

void main() {
  test('concurrent 401s share a single refresh and then retry', () async {
    var refreshCalls = 0;
    final client = ApiClient(
      httpClient: MockClient((request) async {
        if (request.url.path == '/auth/refresh') {
          refreshCalls++;
          // Let the other 401s arrive before the refresh completes.
          await Future<void>.delayed(const Duration(milliseconds: 40));
          return http.Response(
            jsonEncode({
              'accessToken': 'fresh',
              'refreshToken': 'refresh-2',
              'tokenType': 'bearer',
            }),
            200,
          );
        }
        if (request.headers['Authorization'] == 'Bearer fresh') {
          return http.Response(jsonEncode({'ok': true}), 200);
        }
        return http.Response(jsonEncode({'detail': 'Unauthorized'}), 401);
      }),
    );

    client.setTokens(access: 'expired', refresh: 'refresh-1');
    client.onRefresh = (token) async {
      final raw = await client.post(
        '/auth/refresh',
        body: {'refresh_token': token},
        auth: false,
      );
      final data = raw as Map<String, dynamic>;
      client.setTokens(
        access: data['accessToken'] as String,
        refresh: data['refreshToken'] as String,
      );
      return TokenRefreshResult.success;
    };

    final results = await Future.wait([
      client.get('/requests/a'),
      client.get('/requests/b'),
      client.get('/requests/c'),
    ]);

    expect(results, everyElement({'ok': true}));
    expect(refreshCalls, 1);
  });

  test('an invalid refresh token reports an auth failure once', () async {
    var authFailures = 0;
    final client = ApiClient(
      httpClient: MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'Unauthorized'}), 401);
      }),
    );

    client.setTokens(access: 'expired', refresh: 'revoked');
    client.onRefresh = (_) async => TokenRefreshResult.invalidSession;
    client.onAuthFailure = () async => authFailures++;

    await expectLater(client.get('/requests/a'), throwsA(isA<ApiException>()));
    expect(authFailures, 1);
  });
}
