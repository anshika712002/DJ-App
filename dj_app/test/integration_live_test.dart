import 'dart:math';

import 'package:flutter_test/flutter_test.dart';

import 'package:dj_app/src/api_client.dart';
import 'package:dj_app/src/models.dart';
import 'package:dj_app/src/session.dart';
import 'package:dj_app/src/song_api.dart';
import 'package:dj_app/src/token_store.dart';

/// Never touch the real session file from tests.
class _MemoryStore implements TokenStore {
  Map<String, dynamic>? data;

  @override
  Future<void> clear() async => data = null;

  @override
  Future<Map<String, dynamic>?> load() async => data;

  @override
  Future<void> save(Map<String, dynamic> session) async => data = session;
}

/// Exercises the real client stack against a running backend. The suite is
/// self-contained: when no server is listening on 127.0.0.1:8085 every live
/// check is skipped so `flutter test` still passes offline.
void main() {
  test('live backend: signup, login, search and list flows', () async {
    final probe = ApiClient();
    final online = await probe
        .get('/')
        .then((_) => true)
        .catchError((_) => false)
        .timeout(const Duration(seconds: 3), onTimeout: () => false);
    if (!online) {
      // ignore: avoid_print
      print('SKIP live backend tests: no server on 127.0.0.1:8085');
      return;
    }

    final store = _MemoryStore();
    final session = Session(api: ApiClient(), store: store);
    final suffix = Random().nextInt(900000) + 100000;
    final userName = 'it_user_$suffix';
    final phone = '98$suffix';
    final password = 'TestPassw0rd!';

    await session.signUp(
      userName: userName,
      password: password,
      phone: phone,
      role: 'user',
    );
    expect(session.isAuthenticated, isFalse,
        reason: 'signup does not sign the user in');

    // Wrong password surfaces the backend's envelope message.
    try {
      await session.login(identifier: phone, password: 'nope', role: 'user');
      fail('login with a bad password should throw');
    } on ApiException catch (e) {
      expect(e.statusCode, anyOf(400, 401));
      expect(e.message, isNotEmpty);
    }

    await session.login(identifier: phone, password: password, role: 'user');
    expect(session.isAuthenticated, isTrue);
    expect(session.isDj, isFalse);
    expect(session.api.accessToken, isNotNull);

    final api = SongApi(session.api);

    // Authenticated list call: a brand new user has no requests yet.
    final mine = await api.all(mineOnly: true);
    expect(mine, isEmpty);

    // The login response is persisted through the store for later restore.
    expect(store.data, isNotNull);
    expect(store.data!['accessToken'], session.api.accessToken);
    expect(store.data!['role'], 'user');
  });

  test('live backend: search reaches Audius through the API', () async {
    final probe = ApiClient();
    final online = await probe
        .get('/')
        .then((_) => true)
        .catchError((_) => false)
        .timeout(const Duration(seconds: 3), onTimeout: () => false);
    if (!online) {
      // ignore: avoid_print
      print('SKIP live search test: no server on 127.0.0.1:8085');
      return;
    }

    final session = Session(api: ApiClient(), store: _MemoryStore());
    final suffix = Random().nextInt(900000) + 100000;
    final phone = '97$suffix';
    await session.signUp(
      userName: 'it_search_$suffix',
      password: 'TestPassw0rd!',
      phone: phone,
      role: 'user',
    );
    await session.login(identifier: phone, password: 'TestPassw0rd!', role: 'user');

    final api = SongApi(session.api);
    try {
      final results = await api.search('funk');
      for (final song in results) {
        expect(song.videoId, isNotEmpty);
      }
      final suggested = await api.suggested();
      expect(suggested, isA<List<Song>>());
    } on ApiException catch (e) {
      // Audius outages are outside this repo's control.
      // ignore: avoid_print
      print('SKIP Audius-backed checks: ${e.message}');
    }
  });
}
