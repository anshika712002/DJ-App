import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:dj_app/main.dart';
import 'package:dj_app/src/session.dart';
import 'package:dj_app/src/song_api.dart';
import 'package:dj_app/src/token_store.dart';

/// In-memory store so widget tests never touch the real session file.
class _EmptyStore implements TokenStore {
  @override
  Future<void> clear() async {}

  @override
  Future<Map<String, dynamic>?> load() async => null;

  @override
  Future<void> save(Map<String, dynamic> session) async {}
}

Widget _appWith(Session session) => MultiProvider(
      providers: [
        ChangeNotifierProvider<Session>.value(value: session),
        ProxyProvider<Session, SongApi>(
          update: (_, s, _) => SongApi(s.api),
        ),
      ],
      child: const MaterialApp(home: RootScreen()),
    );

void main() {
  testWidgets('shows a splash while the stored session loads',
      (tester) async {
    final session = Session(store: _EmptyStore());
    await tester.pumpWidget(_appWith(session));
    expect(session.isReady, isFalse);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Sign in'), findsNothing);
  });

  testWidgets('signed-out users land on the login screen', (tester) async {
    final session = Session(store: _EmptyStore());
    await session.restore();
    await tester.pumpWidget(_appWith(session));
    await tester.pump();

    expect(session.isReady, isTrue);
    expect(session.isAuthenticated, isFalse);
    expect(find.text('DJ App'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('Email or phone'), findsOneWidget);
    expect(find.text('Password'), findsOneWidget);
  });

  testWidgets('the listener/DJ role toggle is selectable', (tester) async {
    final session = Session(store: _EmptyStore());
    await session.restore();
    await tester.pumpWidget(_appWith(session));
    await tester.pump();

    expect(find.text('Listener'), findsOneWidget);
    await tester.tap(find.text('DJ'));
    await tester.pump();
    expect(find.text('DJ'), findsWidgets);
  });
}
