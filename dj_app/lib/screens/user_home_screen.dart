import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/session.dart';
import 'my_requests_screen.dart';
import 'search_screen.dart';

/// Shell for the listener role: search + "my requests" tabs.
class UserHomeScreen extends StatefulWidget {
  const UserHomeScreen({super.key});

  @override
  State<UserHomeScreen> createState() => _UserHomeScreenState();
}

class _UserHomeScreenState extends State<UserHomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    return Scaffold(
      appBar: AppBar(
        title: Text(_index == 0 ? 'Find music' : 'My requests'),
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
      body: IndexedStack(
        index: _index,
        children: const [
          SearchScreen(),
          MyRequestsScreen(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.search),
            label: 'Search',
          ),
          NavigationDestination(
            icon: Icon(Icons.queue_music),
            label: 'My requests',
          ),
        ],
      ),
    );
  }
}
