import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/models.dart';
import '../src/song_api.dart';
import '../widgets.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen>
    with AutomaticKeepAliveClientMixin {
  final _controller = TextEditingController();
  final _tip = TextEditingController();
  final List<Song> _selected = [];
  List<Song> _songs = [];
  String _mixer = 'overlay';
  bool _loading = false;
  bool _busy = false;
  String? _query;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadSuggested());
  }

  @override
  void dispose() {
    _controller.dispose();
    _tip.dispose();
    super.dispose();
  }

  SongApi get _api => context.read<SongApi>();

  Future<void> _loadSuggested() async {
    setState(() {
      _loading = true;
      _query = null;
    });
    try {
      final results = await _api.suggested();
      if (!mounted) return;
      setState(() => _songs = results);
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _search(String raw) async {
    final query = raw.trim();
    if (query.isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _query = query;
    });
    try {
      final results = await _api.search(query);
      if (!mounted) return;
      setState(() => _songs = results);
      if (results.isEmpty) showInfo(context, 'No tracks found for "$query"');
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _toggle(Song song) {
    setState(() {
      if (_selected.contains(song)) {
        _selected.remove(song);
      } else if (_selected.length < 2) {
        _selected.add(song);
      }
    });
  }

  Future<void> _requestMix() async {
    if (_selected.isEmpty) return;
    final tip = double.tryParse(_tip.text.trim());
    setState(() => _busy = true);
    try {
      final id = await _api.requestMix(
        trackIds: _selected.map((s) => s.videoId).toList(),
        tipAmount: tip,
        mixer: _mixer,
      );
      if (!mounted) return;
      showInfo(context, 'Mix queued (#$id) - track it under "My requests"');
      setState(() {
        _selected.clear();
        _tip.clear();
      });
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final theme = Theme.of(context);
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: TextField(
            controller: _controller,
            textInputAction: TextInputAction.search,
            onSubmitted: _search,
            decoration: InputDecoration(
              hintText: 'Search songs, artists, moods...',
              prefixIcon: const Icon(Icons.search),
              border: const OutlineInputBorder(),
              suffixIcon: IconButton(
                tooltip: 'Search',
                icon: const Icon(Icons.arrow_forward),
                onPressed: () => _search(_controller.text),
              ),
            ),
          ),
        ),
        if (_query != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                Expanded(
                  child: Text('Results for "${_query!}"',
                      style: theme.textTheme.bodySmall),
                ),
                TextButton(
                  onPressed: _loadSuggested,
                  child: const Text('Suggestions'),
                ),
              ],
            ),
          ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _songs.isEmpty
                  ? const EmptyState(
                      icon: Icons.music_off,
                      title: 'Nothing here yet',
                      subtitle: 'Search for a song to get started.',
                    )
                  : RefreshIndicator(
                      onRefresh: _loadSuggested,
                      child: ListView.builder(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: _songs.length,
                        itemBuilder: (context, i) {
                          final song = _songs[i];
                          final checked = _selected.contains(song);
                          final selectable =
                              checked || _selected.length < 2;
                          return _SongTile(
                            song: song,
                            checked: checked,
                            selectable: selectable,
                            onTap: () => _toggle(song),
                          );
                        },
                      ),
                    ),
        ),
        if (_selected.isNotEmpty) _buildSelectionPanel(theme),
      ],
    );
  }

  Widget _buildSelectionPanel(ThemeData theme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh,
        border: Border(top: BorderSide(color: theme.dividerColor)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _selected.map((s) => s.title ?? s.videoId).join('  +  '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall,
                  ),
                ),
                Text('${_selected.length}/2',
                    style: theme.textTheme.bodySmall),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _mixer,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Mixer',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    items: kMixers
                        .map((m) => DropdownMenuItem(
                            value: m,
                            child: Text(m,
                                overflow: TextOverflow.ellipsis)))
                        .toList(),
                    onChanged: (v) =>
                        setState(() => _mixer = v ?? 'overlay'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: TextField(
                    controller: _tip,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Tip (optional)',
                      prefixText: '\$ ',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _busy ? null : _requestMix,
                icon: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.library_add_check),
                label: const Text('Request mix'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SongTile extends StatelessWidget {
  const _SongTile({
    required this.song,
    required this.checked,
    required this.selectable,
    required this.onTap,
  });

  final Song song;
  final bool checked;
  final bool selectable;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: Stack(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: song.thumbnail != null && song.thumbnail!.isNotEmpty
                ? Image.network(
                    song.thumbnail!,
                    width: 52,
                    height: 52,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => const _ThumbnailFallback(),
                  )
                : const _ThumbnailFallback(),
          ),
          if (checked)
            Positioned(
              right: -2,
              bottom: -2,
              child: Icon(Icons.check_circle,
                  size: 18, color: theme.colorScheme.primary),
            ),
        ],
      ),
      title: Text(song.title ?? 'Untitled',
          maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          if (song.artistName != null && song.artistName!.isNotEmpty)
            song.artistName!,
          if (song.duration != null) _formatDuration(song.duration!),
        ].join('  •  '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Checkbox(
        value: checked,
        onChanged: selectable ? (_) => onTap() : null,
      ),
      onTap: selectable ? onTap : null,
    );
  }

  static String _formatDuration(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }
}

class _ThumbnailFallback extends StatelessWidget {
  const _ThumbnailFallback();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 52,
      height: 52,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: const Icon(Icons.music_note, size: 28),
    );
  }
}
