import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'models.dart';
import 'song_api.dart';

/// Loads and refreshes the authenticated user's own requests. There is no
/// realtime channel, so a light poll keeps statuses (processing -> ready) in
/// sync while the backend prepares mixes in the background.
class MyRequestsController extends ChangeNotifier {
  MyRequestsController(this._api);

  final SongApi _api;

  Timer? _timer;
  bool _disposed = false;
  bool _loading = true;
  String? _error;
  List<RequestItem> _items = const [];

  List<RequestItem> get items => _items;
  bool get loading => _loading;
  String? get error => _error;
  bool get isEmpty => _items.isEmpty;

  static const Duration pollInterval = Duration(seconds: 6);

  void start() {
    unawaited(load());
    _timer?.cancel();
    _timer = Timer.periodic(pollInterval, (_) => load(silent: true));
  }

  Future<void> load({bool silent = false}) async {
    if (_disposed) return;
    if (!silent) {
      _loading = _loading && _items.isEmpty;
      _notify();
    }
    try {
      final items = await _api.all();
      if (_disposed) return;
      _items = items;
      _error = null;
    } on ApiException catch (e) {
      if (_disposed) return;
      _error = e.message;
    } catch (_) {
      if (_disposed) return;
      _error = 'Could not refresh your requests.';
    } finally {
      if (!_disposed) {
        _loading = false;
        _notify();
      }
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
