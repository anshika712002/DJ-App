import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'config.dart';

/// Maintains the DJ dashboard's `/ws/dj` connection and re-emits the server's
/// push messages (`new_song_request`, `status_update`), reconnecting with a
/// short backoff when the socket drops.
class LiveQueue {
  LiveQueue({this._token});

  final String Function()? _token;

  Uri _socketUri() {
    final base = Uri.parse(AppConfig.wsUrl('/ws/dj'));
    final token = _token?.call() ?? '';
    if (token.isEmpty) return base;
    return base.replace(queryParameters: {...base.queryParameters, 'token': token});
  }

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  final StreamController<Map<String, dynamic>> _events =
      StreamController<Map<String, dynamic>>.broadcast();
  final StreamController<bool> _connection =
      StreamController<bool>.broadcast();
  bool _disposed = false;
  bool _connected = false;

  Stream<Map<String, dynamic>> get events => _events.stream;
  Stream<bool> get connection => _connection.stream;
  bool get isConnected => _connected;

  void connect() {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    try {
      final channel = WebSocketChannel.connect(_socketUri());
      _channel = channel;
      channel.ready.then((_) {
        if (_disposed) return;
        _connected = true;
        _connection.add(true);
      }).catchError((_) {
        _scheduleReconnect();
      });
      _subscription = channel.stream.listen(
        (raw) {
          if (raw is! String) return;
          try {
            final decoded = jsonDecode(raw);
            if (decoded is Map<String, dynamic>) _events.add(decoded);
          } catch (_) {
            // Ignore malformed frames.
          }
        },
        onError: (_) => _handleDrop(),
        onDone: _handleDrop,
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _handleDrop() {
    if (_connected) {
      _connected = false;
      _connection.add(false);
    }
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _subscription?.cancel();
    _subscription = null;
    _channel = null;
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), connect);
  }

  void dispose() {
    _disposed = true;
    _connected = false;
    _reconnectTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    _events.close();
    _connection.close();
  }
}
