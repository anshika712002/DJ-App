import 'dart:async';

import 'package:flutter/foundation.dart';

import 'models.dart';
import 'song_api.dart';

/// Distinct, mutually-exclusive states for the search surface so the UI never
/// confuses "loading", "no matches" and "request failed".
enum SearchPhase { idle, loading, success, empty, error }

/// Owns all search behaviour: debouncing, minimum query length, stale-response
/// protection and the separate recent-search history.
///
/// The screen only renders what this exposes, which keeps the widget tree free
/// of business logic and makes the sequencing rules unit-testable.
class SongSearchViewModel extends ChangeNotifier {
  SongSearchViewModel(this._api);

  final SongApi _api;

  static const int minQueryLength = 2;
  static const Duration debounceDuration = Duration(milliseconds: 350);

  Timer? _debounce;
  int _sequence = 0;
  bool _disposed = false;

  String _query = '';
  List<Song> _results = const [];
  SearchPhase _phase = SearchPhase.idle;
  String? _error;
  List<String> _history = const [];
  bool _loadingHistory = false;

  String get query => _query;
  List<Song> get results => _results;
  SearchPhase get phase => _phase;
  String? get error => _error;
  List<String> get history => _history;
  bool get loadingHistory => _loadingHistory;

  /// True when the user has not typed enough characters to search yet.
  bool get belowMinimum =>
      _query.trim().isNotEmpty && _query.trim().length < minQueryLength;

  /// Called on every keystroke. Debounces, and never issues a request for a
  /// query shorter than [minQueryLength].
  void onQueryChanged(String raw) {
    _query = raw;
    _debounce?.cancel();

    if (raw.trim().length < minQueryLength) {
      // Invalidate any in-flight request and clear stale results so an old
      // query can never be shown as if it matched the new, shorter one.
      _sequence++;
      _results = const [];
      _phase = SearchPhase.idle;
      _error = null;
      _notify();
      return;
    }

    _debounce = Timer(debounceDuration, () => _run(raw));
    _notify();
  }

  /// Immediate search (search button / keyboard submit).
  Future<void> submit(String raw) {
    _debounce?.cancel();
    _query = raw;
    if (raw.trim().length < minQueryLength) {
      _sequence++;
      _results = const [];
      _phase = SearchPhase.idle;
      _error = null;
      _notify();
      return Future.value();
    }
    return _run(raw);
  }

  /// Re-run the current query (retry button after an error).
  Future<void> retry() {
    final q = _query.trim();
    if (q.length < minQueryLength) return Future.value();
    return _run(q);
  }

  Future<void> _run(String raw) async {
    final query = raw.trim();
    final token = ++_sequence;

    _query = raw;
    _phase = SearchPhase.loading;
    _error = null;
    // Drop the previous query's results immediately so they can never be read
    // as matches for the new query while the request is in flight.
    _results = const [];
    _notify();

    try {
      final youtube = await _api.search(query);
      if (_isStale(token)) return;

      // Local/licensed assets are optional: a failure there must not hide the
      // provider results, so it is swallowed deliberately.
      List<Song> assets = const [];
      try {
        assets = await _api.searchAssets(query);
      } catch (_) {
        assets = const [];
      }
      if (_isStale(token)) return;

      final combined = [...youtube, ...assets];
      _results = combined;
      _phase = combined.isEmpty ? SearchPhase.empty : SearchPhase.success;
      _notify();
      if (combined.isNotEmpty) unawaited(loadHistory());
    } catch (e) {
      if (_isStale(token)) return;
      _results = const [];
      _phase = SearchPhase.error;
      _error = e is Exception ? e.toString() : 'Search failed';
      _notify();
    }
  }

  /// Loads the genuine, clearly-labelled recent searches. History is never used
  /// as the search result list.
  Future<void> loadHistory() async {
    if (_disposed) return;
    _loadingHistory = true;
    _notify();
    try {
      final history = await _api.searchHistory();
      if (_disposed) return;
      _history = history;
    } catch (_) {
      // History is a convenience; failing to load it must not surface an error.
    } finally {
      _loadingHistory = false;
      _notify();
    }
  }

  /// Runs a search for a tapped history entry.
  Future<void> useHistoryQuery(String query) {
    _debounce?.cancel();
    return _run(query);
  }

  /// Clears the current query/results but keeps history intact.
  void clear() {
    _debounce?.cancel();
    _sequence++;
    _query = '';
    _results = const [];
    _phase = SearchPhase.idle;
    _error = null;
    _notify();
  }

  bool _isStale(int token) => _disposed || token != _sequence;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _debounce?.cancel();
    super.dispose();
  }
}
