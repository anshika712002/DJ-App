import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../src/models.dart';
import '../../src/playback.dart';
import '../../src/search_view_model.dart';
import '../../src/session.dart';
import '../../src/song_api.dart';
import '../../theme/app_theme.dart';
import '../../widgets/artwork.dart';
import '../../widgets/layout.dart';
import '../../widgets/song_card.dart';
import '../../widgets/state_views.dart';
import '../../widgets/status_badge.dart';

/// Home: welcome header, prominent search entry point, genuine recent searches,
/// recommendations and a shortcut to the user's own requests.
class UserHomeScreen extends StatefulWidget {
  const UserHomeScreen({
    super.key,
    required this.onOpenSearch,
    required this.onOpenRequests,
  });

  final VoidCallback onOpenSearch;
  final VoidCallback onOpenRequests;

  @override
  State<UserHomeScreen> createState() => _UserHomeScreenState();
}

class _UserHomeScreenState extends State<UserHomeScreen> {
  final _searchController = TextEditingController();

  List<Song> _suggested = const [];
  bool _loadingSuggested = true;
  String? _suggestedError;

  List<RequestItem> _recent = const [];
  bool _loadingRecent = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  SongApi get _api => context.read<SongApi>();
  SongSearchViewModel get _search => context.read<SongSearchViewModel>();

  Future<void> _load() async {
    await Future.wait([_loadSuggested(), _loadRecent()]);
  }

  Future<void> _loadSuggested() async {
    setState(() {
      _loadingSuggested = true;
      _suggestedError = null;
    });
    try {
      final results = await _api.suggested();
      if (!mounted) return;
      setState(() => _suggested = results.take(6).toList());
    } catch (e) {
      if (!mounted) return;
      setState(() => _suggestedError = e.toString());
    } finally {
      if (mounted) setState(() => _loadingSuggested = false);
    }
  }

  Future<void> _loadRecent() async {
    try {
      final items = await _api.all();
      if (!mounted) return;
      setState(() => _recent = items.take(2).toList());
    } catch (_) {
      // Non-critical: the requests tab has its own error handling.
    } finally {
      if (mounted) setState(() => _loadingRecent = false);
    }
  }

  void _runSearch(String raw) {
    if (raw.trim().length < SongSearchViewModel.minQueryLength) {
      widget.onOpenSearch();
      return;
    }
    _search.submit(raw);
    widget.onOpenSearch();
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    final history = context.watch<SongSearchViewModel>().history;

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.only(bottom: AppSpacing.xl),
        children: [
          ConstrainedContent(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _HeroHeader(
                  userName: session.userName,
                  controller: _searchController,
                  onSubmit: _runSearch,
                  onBrowse: widget.onOpenSearch,
                ),
                if (history.isNotEmpty) ...[
                  SectionHeader(
                    title: 'Recent searches',
                    subtitle: 'Tap to search again',
                    trailing: TextButton(
                      onPressed: () => context
                          .read<SongSearchViewModel>()
                          .loadHistory(),
                      child: const Text('Refresh'),
                    ),
                  ),
                  _HistoryRow(
                    history: history,
                    onPick: (q) {
                      _search.useHistoryQuery(q);
                      widget.onOpenSearch();
                    },
                  ),
                ],
                SectionHeader(
                  title: 'Recommended for you',
                  subtitle: 'Trending on the provider right now',
                  trailing: IconButton(
                    tooltip: 'Refresh',
                    onPressed: _loadSuggested,
                    icon: const Icon(Icons.refresh_rounded),
                  ),
                ),
                _SuggestedSection(
                  loading: _loadingSuggested,
                  error: _suggestedError,
                  songs: _suggested,
                  onRetry: _loadSuggested,
                  onPlay: (song) => playTrack(context, _api, song),
                ),
                SectionHeader(
                  title: 'Your requests',
                  subtitle: _loadingRecent
                      ? 'Loading…'
                      : '${_recent.length} recent',
                  trailing: TextButton(
                    onPressed: widget.onOpenRequests,
                    child: const Text('View all'),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  child: _RecentRequests(
                    loading: _loadingRecent,
                    items: _recent,
                    onOpen: widget.onOpenRequests,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroHeader extends StatelessWidget {
  const _HeroHeader({
    required this.userName,
    required this.controller,
    required this.onSubmit,
    required this.onBrowse,
  });

  final String userName;
  final TextEditingController controller;
  final ValueChanged<String> onSubmit;
  final VoidCallback onBrowse;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.fromLTRB(
          AppSpacing.md, AppSpacing.md, AppSpacing.md, AppSpacing.sm),
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        borderRadius: AppRadius.borderLg,
        gradient: const LinearGradient(
          colors: [AppColors.primaryDeep, AppColors.surfaceHigh],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const EqualizerBars(size: 26, color: AppColors.textPrimary),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  userName.isEmpty ? 'Welcome' : 'Welcome back, $userName',
                  style: theme.textTheme.headlineSmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Search the catalogue, build a mix and play it once it is ready.',
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: AppColors.textSecondary),
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: controller,
            textInputAction: TextInputAction.search,
            onSubmitted: onSubmit,
            decoration: InputDecoration(
              hintText: 'Search songs, artists, moods…',
              prefixIcon: const Icon(Icons.search_rounded),
              suffixIcon: IconButton(
                tooltip: 'Search',
                icon: const Icon(Icons.arrow_forward_rounded),
                onPressed: () => onSubmit(controller.text),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: onBrowse,
              icon: const Icon(Icons.explore_outlined),
              label: const Text('Browse all results'),
            ),
          ),
        ],
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.history, required this.onPick});

  final List<String> history;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        itemCount: history.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final query = history[i];
          return ActionChip(
            avatar: const Icon(Icons.history_rounded, size: 16),
            label: Text(query),
            onPressed: () => onPick(query),
          );
        },
      ),
    );
  }
}

class _SuggestedSection extends StatelessWidget {
  const _SuggestedSection({
    required this.loading,
    required this.error,
    required this.songs,
    required this.onRetry,
    required this.onPlay,
  });

  final bool loading;
  final String? error;
  final List<Song> songs;
  final VoidCallback onRetry;
  final ValueChanged<Song> onPlay;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: LoadingView(label: 'Loading recommendations'),
      );
    }
    if (error != null) {
      return ErrorStateView(message: error!, onRetry: onRetry);
    }
    if (songs.isEmpty) {
      return const EmptyStateView(
        icon: Icons.music_off_rounded,
        title: 'No recommendations right now',
        subtitle: 'Try searching for a song above.',
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      child: Column(
        children: [
          for (final song in songs)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: SongCard(
                song: song,
                selectable: false,
                onPlay: () => onPlay(song),
              ),
            ),
        ],
      ),
    );
  }
}

class _RecentRequests extends StatelessWidget {
  const _RecentRequests({
    required this.loading,
    required this.items,
    required this.onOpen,
  });

  final bool loading;
  final List<RequestItem> items;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.md),
          child: LoadingView(),
        ),
      );
    }
    if (items.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              const Icon(Icons.queue_music_rounded, color: AppColors.textMuted),
              const SizedBox(width: 12),
              const Expanded(
                child: Text('You have not requested any songs yet.'),
              ),
              TextButton(onPressed: onOpen, child: const Text('Get started')),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        for (final item in items)
          Card(
            margin: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: ListTile(
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
              leading: Artwork(
                url: item.songs.isNotEmpty ? item.songs.first.artwork : null,
                title: item.mixSongTitle,
                size: 44,
              ),
              title: Text(
                item.mixSongTitle.isEmpty ? 'Mix #${item.id}' : item.mixSongTitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(item.requestedAt),
              trailing: StatusBadge(status: item.status, dense: true),
              onTap: onOpen,
            ),
          ),
      ],
    );
  }
}
