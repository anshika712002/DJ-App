import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:dj_app/src/api_client.dart';
import 'package:dj_app/src/models.dart';
import 'package:dj_app/src/search_view_model.dart';
import 'package:dj_app/src/song_api.dart';

/// Deterministic stand-in for the real provider so tests can control exactly
/// when each query resolves and in which order.
class _FakeSongApi extends SongApi {
  _FakeSongApi() : super(ApiClient());

  final Map<String, Completer<List<Song>>> _pending = {};
  final List<String> searchCalls = [];
  final List<String> assetCalls = [];
  List<String> history = const [];
  int historyCalls = 0;

  @override
  Future<List<Song>> search(String query) {
    searchCalls.add(query);
    final completer = Completer<List<Song>>();
    _pending[query] = completer;
    return completer.future;
  }

  @override
  Future<List<Song>> searchAssets(String query) async {
    assetCalls.add(query);
    return const [];
  }

  @override
  Future<List<String>> searchHistory() async {
    historyCalls++;
    return history;
  }

  void complete(String query, List<Song> songs) => _pending[query]!.complete(songs);
  void fail(String query, Object error) => _pending[query]!.completeError(error);
}

Song _song(String id) =>
    Song.fromJson({'trackId': id, 'sourceType': 'youtube', 'title': id});

void main() {
  late _FakeSongApi api;
  late SongSearchViewModel vm;

  setUp(() {
    api = _FakeSongApi();
    vm = SongSearchViewModel(api);
    addTearDown(vm.dispose);
  });

  test('does not search until the query reaches the minimum length', () async {
    vm.onQueryChanged('a');
    await pumpEventQueue();

    expect(api.searchCalls, isEmpty);
    expect(vm.phase, SearchPhase.idle);
    expect(vm.belowMinimum, isTrue);
  });

  test('debounces keystrokes into a single request', () async {
    vm.onQueryChanged('ni');
    vm.onQueryChanged('nig');
    vm.onQueryChanged('nigh');
    await pumpEventQueue();

    // Still inside the debounce window: nothing fired yet.
    expect(api.searchCalls, isEmpty);

    await Future<void>.delayed(
        SongSearchViewModel.debounceDuration + const Duration(milliseconds: 60));

    expect(api.searchCalls, ['nigh']);
  });

  test('drops stale results when a newer query resolves first', () async {
    unawaited(vm.submit('abc'));
    unawaited(vm.submit('abcd'));
    await pumpEventQueue();

    expect(api.searchCalls, ['abc', 'abcd']);

    api.complete('abcd', [_song('B')]);
    await pumpEventQueue();
    expect(vm.results.single.trackId, 'B');

    // The earlier query resolves last and must not overwrite the newer one.
    api.complete('abc', [_song('A')]);
    await pumpEventQueue();
    expect(vm.results.single.trackId, 'B');
    expect(vm.phase, SearchPhase.success);
  });

  test('clears stale results when the query shrinks below the minimum',
      () async {
    unawaited(vm.submit('hello'));
    await pumpEventQueue();
    api.complete('hello', [_song('h')]);
    await pumpEventQueue();
    expect(vm.results, hasLength(1));

    vm.onQueryChanged('h');
    await pumpEventQueue();
    expect(vm.results, isEmpty);
    expect(vm.phase, SearchPhase.idle);
  });

  test('an out-of-range earlier response never replaces cleared results',
      () async {
    unawaited(vm.submit('hello'));
    await pumpEventQueue();

    // Shrink the query before the in-flight request resolves.
    vm.onQueryChanged('h');
    await pumpEventQueue();

    api.complete('hello', [_song('h')]);
    await pumpEventQueue();

    expect(vm.results, isEmpty);
    expect(vm.phase, SearchPhase.idle);
  });

  test('reports an empty result set distinctly from success', () async {
    unawaited(vm.submit('nothing'));
    await pumpEventQueue();
    api.complete('nothing', const []);
    await pumpEventQueue();

    expect(vm.phase, SearchPhase.empty);
    expect(vm.results, isEmpty);
  });

  test('surfaces provider failures as an error phase', () async {
    unawaited(vm.submit('boom'));
    await pumpEventQueue();
    api.fail('boom', const ApiException(500, 'provider exploded'));
    await pumpEventQueue();

    expect(vm.phase, SearchPhase.error);
    expect(vm.error, contains('provider exploded'));
    expect(vm.results, isEmpty);
  });

  test('loads recent searches only after a successful query', () async {
    api.history = ['nightcall'];

    unawaited(vm.submit('hello'));
    await pumpEventQueue();
    expect(vm.history, isEmpty);
    expect(api.historyCalls, 0);

    api.complete('hello', [_song('h')]);
    await pumpEventQueue();
    await pumpEventQueue();

    expect(vm.history, ['nightcall']);
  });
}
