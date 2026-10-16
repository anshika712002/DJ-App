import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../src/session.dart';
import '../theme/app_theme.dart';
import '../widgets/layout.dart';

/// Profile/settings screen. Read-only summary of the authenticated account
/// plus sign out.
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    final user = session.current;

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        ConstrainedContent(
          maxWidth: 640,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _ProfileHeader(userName: user?.userName ?? ''),
              const SizedBox(height: AppSpacing.lg),
              _InfoTile(
                icon: Icons.alternate_email_rounded,
                label: 'Email',
                value: user?.email,
              ),
              _InfoTile(
                icon: Icons.phone_rounded,
                label: 'Phone',
                value: user?.phone,
              ),
              const SizedBox(height: AppSpacing.lg),
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.danger,
                  side: const BorderSide(color: AppColors.danger),
                ),
                onPressed: () => _signOut(context),
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Sign out'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _signOut(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
            'You will need to sign in again to search and manage requests.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await context.read<Session>().logout();
    }
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.userName});

  final String userName;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final initial =
        userName.trim().isEmpty ? '?' : userName.trim()[0].toUpperCase();
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: AppColors.brandGradient,
        borderRadius: AppRadius.borderLg,
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 32,
            backgroundColor: Colors.black.withValues(alpha: 0.25),
            child: Text(
              initial,
              style: const TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  color: Colors.white),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  userName.isEmpty ? 'Signed in' : userName,
                  style: theme.textTheme.headlineSmall
                      ?.copyWith(color: Colors.white),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(
                      Icons.music_note_rounded,
                      size: 16,
                      color: Colors.white,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'Music Mixer account',
                      style: const TextStyle(color: Colors.white70),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  const _InfoTile({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    final hasValue = (value ?? '').trim().isNotEmpty;
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: ListTile(
        leading: Icon(icon, color: AppColors.primary),
        title: Text(label),
        subtitle: Text(hasValue ? value! : 'Not provided'),
      ),
    );
  }
}
