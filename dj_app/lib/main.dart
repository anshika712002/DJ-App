import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/login_screen.dart';
import 'screens/user/user_shell.dart';
import 'src/session.dart';
import 'src/song_api.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MusicMixerApp());
}

class MusicMixerApp extends StatelessWidget {
  const MusicMixerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<Session>(create: (_) => Session()..restore()),
        ProxyProvider<Session, SongApi>(
          update: (_, session, _) => SongApi(session.api),
        ),
      ],
      child: MaterialApp(
        title: 'Music Mixer',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        home: const RootScreen(),
      ),
    );
  }
}

/// Decides which screen to show: splash while the stored session loads, then
/// login for anonymous users, otherwise the single application shell.
class RootScreen extends StatelessWidget {
  const RootScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    if (!session.isReady) {
      return const Scaffold(body: LoadingSplash());
    }
    if (!session.isAuthenticated) return const LoginScreen();
    return const UserShell();
  }
}

class LoadingSplash extends StatelessWidget {
  const LoadingSplash({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: SizedBox(
        width: 40,
        height: 40,
        child: CircularProgressIndicator(strokeWidth: 3),
      ),
    );
  }
}
