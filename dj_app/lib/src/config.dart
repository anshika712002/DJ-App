/// Compile-time configuration.
///
/// Override at build/run time, e.g.:
///   flutter run --dart-define=API_BASE=http://10.0.2.2:8085   # Android emulator
///   flutter run --dart-define=API_BASE=http://127.0.0.1:8085  # desktop / web
class AppConfig {
  static const String apiBase = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'http://127.0.0.1:8085',
  );

  static String httpUrl(String path) => '$apiBase$path';

  static String wsUrl(String path) => '${apiBase.replaceFirst('http', 'ws')}$path';
}
