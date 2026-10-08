import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/dj_dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'screens/user_home_screen.dart';
import 'src/session.dart';
import 'src/song_api.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const DjApp());
}

class DjApp extends StatelessWidget {
  const DjApp({super.key});

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
        title: 'DJ App',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          brightness: Brightness.dark,
          colorScheme: ColorScheme.fromSeed(
            seedColor: Colors.deepPurple,
            brightness: Brightness.dark,
          ),
          inputDecorationTheme: const InputDecorationTheme(
            border: OutlineInputBorder(),
          ),
        ),
        home: const RootScreen(),
      ),
    );
  }
}

/// Decides which shell to show: splash while the stored session loads, then
/// login for anonymous users, or the role-specific home.
class RootScreen extends StatelessWidget {
  const RootScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    if (!session.isReady) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (!session.isAuthenticated) return const LoginScreen();
    if (session.isDj) return const DjDashboardScreen();
    return const UserHomeScreen();
  }
}
