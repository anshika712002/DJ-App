import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../src/my_requests_controller.dart';
import '../../src/search_view_model.dart';
import '../../src/session.dart';
import '../../src/song_api.dart';
import '../../widgets/app_shell.dart';
import '../profile_screen.dart';
import 'my_requests_screen.dart';
import 'search_screen.dart';
import 'user_home_screen.dart';

/// Application shell for the single user role. Owns the search and request
/// controllers so state survives tab switches.
class UserShell extends StatefulWidget {
  const UserShell({super.key});

  @override
  State<UserShell> createState() => _UserShellState();
}

class _UserShellState extends State<UserShell> {
  int _index = 0;

  static const _destinations = [
    AppDestination(
      icon: Icons.home_outlined,
      selectedIcon: Icons.home_rounded,
      label: 'Home',
    ),
    AppDestination(
      icon: Icons.search_rounded,
      selectedIcon: Icons.search_rounded,
      label: 'Search',
    ),
    AppDestination(
      icon: Icons.queue_music_outlined,
      selectedIcon: Icons.queue_music_rounded,
      label: 'Requests',
    ),
    AppDestination(
      icon: Icons.person_outline_rounded,
      selectedIcon: Icons.person_rounded,
      label: 'Profile',
    ),
  ];

  void _openSearch() => setState(() => _index = 1);
  void _openRequests() => setState(() => _index = 2);

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<SongSearchViewModel>(
          create: (ctx) => SongSearchViewModel(ctx.read<SongApi>())..loadHistory(),
        ),
        ChangeNotifierProvider<MyRequestsController>(
          create: (ctx) => MyRequestsController(ctx.read<SongApi>())..start(),
        ),
      ],
      child: Builder(
        builder: (context) {
          return AppShell(
            destinations: _destinations,
            selectedIndex: _index,
            onSelect: (i) => setState(() => _index = i),
            brandLabel: 'Music Mixer',
            title: session.userName.isEmpty ? 'Music Mixer' : session.userName,
            subtitle: 'Search, mix and play',
            actions: [
              IconButton(
                tooltip: 'Sign out',
                icon: const Icon(Icons.logout_rounded),
                onPressed: () => context.read<Session>().logout(),
              ),
              const SizedBox(width: 8),
            ],
            body: IndexedStack(
              index: _index,
              children: [
                UserHomeScreen(onOpenSearch: _openSearch, onOpenRequests: _openRequests),
                SearchScreen(onViewRequests: _openRequests),
                const MyRequestsScreen(),
                const ProfileScreen(),
              ],
            ),
          );
        },
      ),
    );
  }
}
