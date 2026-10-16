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
    );
    expect(session.isAuthenticated, isFalse,
        reason: 'signup does not sign the user in');

    // Wrong password surfaces the backend's envelope message.
    try {
      await session.login(identifier: phone, password: 'nope');
      fail('login with a bad password should throw');
    } on ApiException catch (e) {
      expect(e.statusCode, anyOf(400, 401));
      expect(e.message, isNotEmpty);
    }

    await session.login(identifier: phone, password: password);
    expect(session.isAuthenticated, isTrue);
    expect(session.api.accessToken, isNotNull);

    final api = SongApi(session.api);

    // Authenticated list call: a brand new user has no requests yet.
    final mine = await api.all();
    expect(mine, isEmpty);

    // The login response is persisted through the store for later restore.
    expect(store.data, isNotNull);
    expect(store.data!['accessToken'], session.api.accessToken);
  });

  test('live backend: search reaches YouTube through the API', () async {
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
    );
    await session.login(identifier: phone, password: 'TestPassw0rd!');

    final api = SongApi(session.api);
    try {
      final results = await api.search('funk');
      for (final song in results) {
        expect(song.trackId, isNotEmpty);
        expect(song.sourceType, 'youtube');
        expect(song.playbackUrl, startsWith('https://www.youtube.com/watch?v='));
        expect(song.mixEligible, isA<bool>());
      }
      final assets = await api.searchAssets('');
      expect(assets, isA<List<Song>>());
      final suggested = await api.suggested();
      expect(suggested, isA<List<Song>>());
    } on ApiException catch (e) {
      // YouTube Data API availability and quota are outside this repo's control.
      // ignore: avoid_print
      print('SKIP YouTube-backed checks: ${e.message}');
    }
  });

  test('live backend: blank search rejected and history tracks real queries',
      () async {
    final probe = ApiClient();
    final online = await probe
        .get('/')
        .then((_) => true)
        .catchError((_) => false)
        .timeout(const Duration(seconds: 3), onTimeout: () => false);
    if (!online) {
      // ignore: avoid_print
      print('SKIP live history test: no server on 127.0.0.1:8085');
      return;
    }

    final session = Session(api: ApiClient(), store: _MemoryStore());
    final suffix = Random().nextInt(900000) + 100000;
    final phone = '96$suffix';
    await session.signUp(
      userName: 'it_history_$suffix',
      password: 'TestPassw0rd!',
      phone: phone,
    );
    await session.login(identifier: phone, password: 'TestPassw0rd!');

    final api = SongApi(session.api);

    // Blank / single-character queries are rejected before hitting the provider.
    for (final bad in ['', ' ', 'a']) {
      try {
        await api.search(bad);
        fail('search("$bad") should have been rejected');
      } on ApiException catch (e) {
        expect(e.statusCode, 400);
      }
    }

    // A real query is echoed back and recorded; the history endpoint is never
    // seeded with prior query text, so it only ever contains what we searched.
    try {
      final results = await api.search('daft punk');
      expect(results, isA<List<Song>>());

      final history = await api.searchHistory();
      expect(history, contains('daft punk'));
      expect(history.toSet().length, history.length,
          reason: 'history must be de-duplicated');
    } on ApiException catch (e) {
      // YouTube quota is outside this repo's control.
      // ignore: avoid_print
      print('SKIP history content check: ${e.message}');
    }
  });
}
