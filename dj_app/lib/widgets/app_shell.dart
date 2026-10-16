import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Navigation destination description shared by the bottom bar and rail.
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

/// Responsive application shell: a bottom navigation bar on compact screens and
/// a navigation rail with a wider content area on desktop windows.
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
    final wide = MediaQuery.sizeOf(context).width >= 760;
    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            _Rail(
              destinations: destinations,
              selectedIndex: selectedIndex,
              onSelect: onSelect,
              brandLabel: brandLabel,
            ),
            const VerticalDivider(width: 1),
            Expanded(
              child: Column(
                children: [
                  _Header(title: title, subtitle: subtitle, actions: actions),
                  Expanded(child: body),
                ],
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(title, style: Theme.of(context).appBarTheme.titleTextStyle),
            if (subtitle != null)
              Text(
                subtitle!,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: AppColors.textSecondary),
              ),
          ],
        ),
        actions: actions,
      ),
      body: body,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: onSelect,
        destinations: destinations
            .map((d) => NavigationDestination(
                  icon: Icon(d.icon),
                  selectedIcon: Icon(d.selectedIcon),
                  label: d.label,
                ))
            .toList(),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.title, this.subtitle, this.actions = const []});

  final String title;
  final String? subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 16, 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.headlineSmall),
                if (subtitle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      subtitle!,
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(color: AppColors.textSecondary),
                    ),
                  ),
              ],
            ),
          ),
          ...actions,
        ],
      ),
    );
  }
}

class _Rail extends StatelessWidget {
  const _Rail({
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    this.brandLabel,
  });

  final List<AppDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final String? brandLabel;

  @override
  Widget build(BuildContext context) {
    return NavigationRail(
      selectedIndex: selectedIndex,
      onDestinationSelected: onSelect,
      labelType: NavigationRailLabelType.all,
      backgroundColor: AppColors.surface,
      leading: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Column(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                gradient: AppColors.brandGradient,
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.graphic_eq, color: Colors.white),
            ),
            if (brandLabel != null) ...[
              const SizedBox(height: 8),
              Text(
                brandLabel!,
                style: Theme.of(context)
                    .textTheme
                    .labelSmall
                    ?.copyWith(color: AppColors.textSecondary),
              ),
            ],
          ],
        ),
      ),
      destinations: destinations
          .map((d) => NavigationRailDestination(
                icon: Icon(d.icon),
                selectedIcon: Icon(d.selectedIcon),
                label: Text(d.label),
              ))
          .toList(),
    );
  }
}
