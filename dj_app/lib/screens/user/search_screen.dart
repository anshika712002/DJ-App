import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../src/models.dart';
import '../../src/playback.dart';
import '../../src/search_view_model.dart';
import '../../src/song_api.dart';
import '../../theme/app_theme.dart';
import '../../widgets/feedback.dart';
import '../../widgets/layout.dart';
import '../../widgets/song_card.dart';
import '../../widgets/state_views.dart';

/// Search: debounced live results, minimum query length, stale-safe updates,
/// and a mix builder that submits to the real backend.
class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.onViewRequests});

  final VoidCallback onViewRequests;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  final List<Song> _selected = [];
  String _mixer = 'overlay';
  bool _busy = false;

  SongSearchViewModel get _search => context.read<SongSearchViewModel>();
  SongApi get _api => context.read<SongApi>();

  @override
  void initState() {
    super.initState();
    _controller.text = _search.query;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _clear() {
    _controller.clear();
    _search.clear();
  }

  void _toggle(Song song) {
    setState(() {
      if (_selected.contains(song)) {
        _selected.remove(song);
      } else if (_selected.length < 2) {
        _selected.add(song);
      } else {
        showInfo(context, 'You can mix up to two tracks at a time.');
      }
    });
  }

  Future<void> _requestMix() async {
    if (_selected.isEmpty || _busy) return;
    setState(() => _busy = true);
    try {
      final id = await _api.requestMix(
        tracks: _selected,
        mixer: _selected.length == 1 ? 'without-mixing' : _mixer,
      );
      if (!mounted) return;
      setState(() {
        _selected.clear();
      });
      ScaffoldMessenger.of(context).hideCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Mix #$id is being prepared. Track it under Requests.'),
          action: SnackBarAction(
            label: 'View requests',
            onPressed: widget.onViewRequests,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showApiError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<SongSearchViewModel>();
    return Column(
      children: [
        ConstrainedContent(
          maxWidth: 720,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.md, AppSpacing.md, AppSpacing.md, AppSpacing.sm),
            child: TextField(
              controller: _controller,
              textInputAction: TextInputAction.search,
              onChanged: _search.onQueryChanged,
              onSubmitted: _search.submit,
              decoration: InputDecoration(
                hintText: 'Search songs, artists, keywords…',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_controller.text.isNotEmpty)
                      IconButton(
                        tooltip: 'Clear',
                        icon: const Icon(Icons.close_rounded),
                        onPressed: _clear,
                      ),
                    IconButton(
                      tooltip: 'Search',
                      icon: const Icon(Icons.arrow_forward_rounded),
                      onPressed: () => _search.submit(_controller.text),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        if (vm.phase == SearchPhase.loading)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: LinearProgressIndicator(minHeight: 3),
          ),
        Expanded(
          child: ConstrainedContent(
            maxWidth: 900,
            child: _buildBody(vm),
          ),
        ),
        if (_selected.isNotEmpty) _buildSelectionPanel(context),
      ],
    );
  }

  Widget _buildBody(SongSearchViewModel vm) {
    switch (vm.phase) {
      case SearchPhase.idle:
        return _IdleView(
          history: vm.history,
          onPick: (q) {
            _controller.text = q;
            _search.useHistoryQuery(q);
          },
        );
      case SearchPhase.loading:
        return const LoadingView(label: 'Searching…');
      case SearchPhase.error:
        return ErrorStateView(message: vm.error ?? 'Search failed', onRetry: vm.retry);
      case SearchPhase.empty:
        return EmptyStateView(
          icon: Icons.search_off_rounded,
          title: 'No matches for "${vm.query.trim()}"',
          subtitle: 'Try a different spelling, a shorter keyword or a related artist.',
        );
      case SearchPhase.success:
        return ListView.builder(
          key: const ValueKey('results'),
          padding: const EdgeInsets.all(AppSpacing.md),
          itemCount: vm.results.length + 1,
          itemBuilder: (context, i) {
            if (i == 0) {
              return Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  'Results for "${vm.query.trim()}"',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: AppColors.textSecondary),
                ),
              );
            }
            final song = vm.results[i - 1];
            final checked = _selected.contains(song);
            final selectable = checked || _selected.length < 2;
            return Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: SongCard(
                song: song,
                selected: checked,
                selectable: selectable,
                onToggle: () => _toggle(song),
                onPlay: () => playTrack(context, _api, song),
              ),
            );
          },
        );
    }
  }

  Widget _buildSelectionPanel(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.md, AppSpacing.md, AppSpacing.md, AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.surfaceHigh,
        border: Border(top: BorderSide(color: AppColors.outline)),
        boxShadow: const [
          BoxShadow(color: Colors.black54, blurRadius: 16, offset: Offset(0, -4)),
        ],
      ),
      child: SafeArea(
        top: false,
        child: ConstrainedContent(
          maxWidth: 900,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.tune_rounded, size: 18, color: AppColors.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _selected.map((s) => s.title ?? s.trackId).join('  +  '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall,
                    ),
                  ),
                  Text('${_selected.length}/2', style: theme.textTheme.bodySmall),
                  IconButton(
                    tooltip: 'Clear selection',
                    icon: const Icon(Icons.close_rounded, size: 18),
                    onPressed: () => setState(_selected.clear),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              DropdownButtonFormField<String>(
                initialValue: _mixer,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Mixer',
                  isDense: true,
                ),
                items: kMixers
                    .map((m) => DropdownMenuItem(
                          value: m,
                          child: Text(m, overflow: TextOverflow.ellipsis),
                        ))
                    .toList(),
                onChanged: (v) => setState(() => _mixer = v ?? 'overlay'),
              ),
              const SizedBox(height: AppSpacing.sm),
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
                      : const Icon(Icons.library_add_check_rounded),
                  label: Text(_selected.length == 1
                      ? 'Request song'
                      : 'Request mix'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _IdleView extends StatelessWidget {
  const _IdleView({required this.history, required this.onPick});

  final List<String> history;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (history.isNotEmpty) ...[
            Text('Recent searches', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final q in history)
                  ActionChip(
                    avatar: const Icon(Icons.history_rounded, size: 16),
                    label: Text(q),
                    onPressed: () => onPick(q),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
          const EmptyStateView(
            icon: Icons.search_rounded,
            title: 'Find your next track',
            subtitle:
                'Type at least 2 characters. Results update automatically as you search.',
          ),
        ],
      ),
    );
  }
}
