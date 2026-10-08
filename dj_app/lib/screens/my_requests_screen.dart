import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/audio_player.dart';
import '../src/models.dart';
import '../src/song_api.dart';
import '../widgets.dart';

/// The listener's own requests. Polls the backend so status changes made by
/// the DJ show up without any extra wiring.
class MyRequestsScreen extends StatefulWidget {
  const MyRequestsScreen({super.key});

  @override
  State<MyRequestsScreen> createState() => _MyRequestsScreenState();
}

class _MyRequestsScreenState extends State<MyRequestsScreen>
    with AutomaticKeepAliveClientMixin {
  Timer? _timer;
  List<RequestItem> _items = [];
  bool _loading = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _load();
      _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  SongApi get _api => context.read<SongApi>();

  Future<void> _load() async {
    try {
      final items = await _api.all(mineOnly: true);
      if (!mounted) return;
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (_) {
      // Keep the previous list on a transient failure; the next tick retries.
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _play(RequestItem item) async {
    final url = _api.audioUrl(item);
    if (url == null) {
      showInfo(context, 'The mix is still being prepared - check back shortly');
      return;
    }
    try {
      await playUrl(url);
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading && _items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty) {
      return const EmptyState(
        icon: Icons.queue_music_outlined,
        title: 'No requests yet',
        subtitle: 'Pick up to two songs under Search and request a mix.',
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        itemCount: _items.length,
        itemBuilder: (context, i) {
          final item = _items[i];
          final canPlay = item.mixedAudioUrl != null;
          return RequestCard(
            item: item,
            canPlay: canPlay,
            onPlay: () => _play(item),
          );
        },
      ),
    );
  }
}
