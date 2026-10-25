import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import 'player_bar.dart';

/// Navigation destination description shared by the bottom bar.
class AppDestination {
  const AppDestination({
    required this.icon,
    required this.selectedIcon,
    required this.label,
  });

  final IconData icon;
  final IconData selectedIcon;
  final String label;
}

/// Mobile-style application shell: a compact app bar, content and the player
/// docked above a bottom navigation bar. Wide windows are framed by
/// `MobileFrame` in `main.dart`, so the same layout is used everywhere.
class AppShell extends StatelessWidget {
  const AppShell({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    required this.body,
    required this.title,
    this.subtitle,
    this.actions = const [],
    this.brandLabel,
  });

  final List<AppDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final Widget body;
  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final String? brandLabel;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: brandLabel == null ? null : const _BrandMark(),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).appBarTheme.titleTextStyle,
            ),
            if (subtitle != null)
              Text(
                subtitle!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall
                    ?.copyWith(color: AppColors.textSecondary),
              ),
          ],
        ),
        actions: [...actions, const SizedBox(width: 8)],
      ),
      body: body,
      bottomNavigationBar: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const PlayerBar(),
          NavigationBar(
            selectedIndex: selectedIndex,
            onDestinationSelected: onSelect,
            destinations: destinations
                .map(
                  (d) => NavigationDestination(
                    icon: Icon(d.icon),
                    selectedIcon: Icon(d.selectedIcon),
                    label: d.label,
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _BrandMark extends StatelessWidget {
  const _BrandMark();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 34,
        height: 34,
        decoration: const BoxDecoration(
          gradient: AppColors.brandGradient,
          shape: BoxShape.circle,
        ),
        child: const Icon(Icons.graphic_eq, color: Colors.white, size: 20),
      ),
    );
  }
}
