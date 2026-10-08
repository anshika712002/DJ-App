import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/audio_player.dart';
import '../src/live_queue.dart';
import '../src/models.dart';
import '../src/session.dart';
import '../src/song_api.dart';
import '../widgets.dart';

/// The DJ's control room: live queue of requests with accept / reject /
/// status transitions, refreshed by polling and by the `/ws/dj` push channel.
class DjDashboardScreen extends StatefulWidget {
  const DjDashboardScreen({super.key});

  @override
  State<DjDashboardScreen> createState() => _DjDashboardScreenState();
}

class _DjDashboardScreenState extends State<DjDashboardScreen> {
  late final LiveQueue _queue;
  StreamSubscription<Map<String, dynamic>>? _eventSub;
  StreamSubscription<bool>? _connectionSub;
  Timer? _timer;
  List<RequestItem> _items = [];
  String? _filter;
  bool _loading = true;
  bool _busy = false;
  bool _connected = false;

  @override
  void initState() {
    super.initState();
    // The socket is JWT-gated server side, so it re-reads the current access
    // token on every (re)connect attempt.
    _queue = LiveQueue(
      token: () => context.read<Session>().api.accessToken ?? '',
    );
    _eventSub = _queue.events.listen((_) => _load());
    _connectionSub = _queue.connection.listen((connected) {
      if (mounted) setState(() => _connected = connected);
    });
    _queue.connect();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _load();
      _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _eventSub?.cancel();
    _connectionSub?.cancel();
    _queue.dispose();
    super.dispose();
  }

  SongApi get _api => context.read<SongApi>();

  Future<void> _load() async {
    try {
      final items = await _api.all(mineOnly: false, status: _filter);
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _run(Future<void> Function() action, String done) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      showInfo(context, done);
      await _load();
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _play(RequestItem item) async {
    final url = _api.audioUrl(item);
    if (url == null) {
      showInfo(context, 'The mix is still being prepared');
      return;
    }
    try {
      await playUrl(url);
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    }
  }

  List<Widget> _actionsFor(RequestItem item) {
    switch (item.status) {
      case 'pending':
        return [
          TextButton(
            onPressed:
                _busy ? null : () => _run(() => _api.reject(item.id), 'Request rejected'),
            child: const Text('Reject'),
          ),
          FilledButton(
            onPressed:
                _busy ? null : () => _run(() => _api.accept(item.id), 'Request accepted'),
            child: const Text('Accept'),
          ),
        ];
      case 'accepted':
        return [
          TextButton(
            onPressed:
                _busy ? null : () => _run(() => _api.reject(item.id), 'Request rejected'),
            child: const Text('Reject'),
          ),
          FilledButton.tonal(
            onPressed: _busy
                ? null
                : () => _run(
                      () => _api.updateStatus(item.id, 'playing'),
                      'Marked as playing',
                    ),
            child: const Text('Play'),
          ),
        ];
      case 'playing':
        return [
          FilledButton.tonal(
            onPressed: _busy
                ? null
                : () => _run(
                      () => _api.updateStatus(item.id, 'played'),
                      'Marked as played',
                    ),
            child: const Text('Done'),
          ),
        ];
      default:
        return const [];
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('DJ Dashboard'),
            const SizedBox(width: 10),
            Icon(
              Icons.circle,
              size: 10,
              color: _connected ? Colors.greenAccent : Colors.redAccent,
            ),
            const SizedBox(width: 4),
            Text(
              _connected ? 'live' : 'offline',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: Center(
              child: Text(session.userName,
                  style: Theme.of(context).textTheme.bodySmall),
            ),
          ),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<Session>().logout(),
          ),
        ],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 54,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              children: [
                _filterChip(null, 'All'),
                for (final s in const [
                  'pending',
                  'accepted',
                  'playing',
                  'played',
                  'rejected'
                ])
                  _filterChip(s, statusLabel(s)),
              ],
            ),
          ),
          Expanded(
            child: _loading && _items.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : _items.isEmpty
                    ? EmptyState(
                        icon: Icons.library_music_outlined,
                        title: _filter == null
                            ? 'No requests in the queue'
                            : 'No ${statusLabel(_filter!)} requests',
                        subtitle:
                            'New requests appear here instantly over the live channel.',
                      )
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: ListView.builder(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.all(12),
                          itemCount: _items.length,
                          itemBuilder: (context, i) {
                            final item = _items[i];
                            return RequestCard(
                              item: item,
                              canPlay: item.mixedAudioUrl != null,
                              onPlay: () => _play(item),
                              actions: _actionsFor(item),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _filterChip(String? value, String label) {
    final selected = _filter == value;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: FilterChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) {
          setState(() => _filter = value);
          _load();
        },
      ),
    );
  }
}
