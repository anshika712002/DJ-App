import 'package:flutter/material.dart';

/// Central design tokens for the DJ console aesthetic: near-black surfaces,
/// electric violet / magenta accents and restrained neon highlights.
class AppColors {
  AppColors._();

  static const background = Color(0xFF0A0A0F);
  static const surface = Color(0xFF121220);
  static const surfaceHigh = Color(0xFF1A1A2B);
  static const surfaceHighest = Color(0xFF232338);
  static const outline = Color(0xFF2E2E44);

  static const primary = Color(0xFFA855F7);
  static const primaryDeep = Color(0xFF7C3AED);
  static const secondary = Color(0xFFEC4899);
  static const tertiary = Color(0xFF22D3EE);
  static const neon = Color(0xFFD946EF);

  static const textPrimary = Color(0xFFF5F3FF);
  static const textSecondary = Color(0xFFA8A8BE);
  static const textMuted = Color(0xFF6B6B80);

  static const success = Color(0xFF34D399);
  static const warning = Color(0xFFF5B301);
  static const danger = Color(0xFFF87171);
  static const info = Color(0xFF38BDF8);

  static const brandGradient = LinearGradient(
    colors: [primaryDeep, primary, secondary],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const glowGradient = LinearGradient(
    colors: [Color(0x33A855F7), Color(0x000A0A0F)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );
}

class AppRadius {
  AppRadius._();

  static const sm = 10.0;
  static const md = 16.0;
  static const lg = 22.0;
  static const pill = 999.0;

  static const borderSm = BorderRadius.all(Radius.circular(sm));
  static const borderMd = BorderRadius.all(Radius.circular(md));
  static const borderLg = BorderRadius.all(Radius.circular(lg));
  static const borderPill = BorderRadius.all(Radius.circular(pill));
}

class AppSpacing {
  AppSpacing._();

  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}

/// Visual metadata for a request status, shared by badges and timelines.
class StatusVisual {
  final String label;
  final Color color;
  final IconData icon;
  final String description;

  const StatusVisual(this.label, this.color, this.icon, this.description);
}

StatusVisual statusVisual(String status) {
  switch (status) {
    case 'pending':
      return const StatusVisual(
        'Processing',
        AppColors.warning,
        Icons.hourglass_top_rounded,
        'Your mix is being prepared. This usually takes a moment.',
      );
    case 'accepted':
    case 'ready':
    case 'completed':
      return const StatusVisual(
        'Ready',
        AppColors.success,
        Icons.play_circle_outline,
        'Your mix is ready - tap play to listen.',
      );
    case 'playing':
      return const StatusVisual(
        'Playing',
        AppColors.primary,
        Icons.graphic_eq,
        'Your mix is playing.',
      );
    case 'played':
      return const StatusVisual(
        'Played',
        AppColors.success,
        Icons.done_all,
        'Your mix finished playing.',
      );
    case 'failed':
      return const StatusVisual(
        'Failed',
        AppColors.danger,
        Icons.error_outline,
        'We could not prepare this mix. You can try again.',
      );
    case 'rejected':
      return const StatusVisual(
        'Unavailable',
        AppColors.danger,
        Icons.cancel_outlined,
        'This mix could not be prepared.',
      );
    default:
      return StatusVisual(
        status.isEmpty ? 'Unknown' : status,
        AppColors.textMuted,
        Icons.help_outline,
        'Status unknown.',
      );
  }
}

Color statusColor(String status) => statusVisual(status).color;

/// A mix is playable only once the backend finished preparing it. The legacy
/// accepted/playing/played values are kept for older rows in the database.
bool isPlayableStatus(String status) => const {
      'ready',
      'completed',
      'accepted',
      'playing',
      'played',
    }.contains(status);

ThemeData buildAppTheme() {
  final base = ColorScheme.fromSeed(
    seedColor: AppColors.primary,
    brightness: Brightness.dark,
  );

  final scheme = base.copyWith(
    primary: AppColors.primary,
    onPrimary: Colors.white,
    secondary: AppColors.secondary,
    onSecondary: Colors.white,
    tertiary: AppColors.tertiary,
    surface: AppColors.surface,
    onSurface: AppColors.textPrimary,
    surfaceContainerLow: AppColors.background,
    surfaceContainer: AppColors.surface,
    surfaceContainerHigh: AppColors.surfaceHigh,
    surfaceContainerHighest: AppColors.surfaceHighest,
    outline: AppColors.outline,
    error: AppColors.danger,
  );

  final textTheme = Typography.material2021(platform: TargetPlatform.windows)
      .white
      .apply(
        bodyColor: AppColors.textPrimary,
        displayColor: AppColors.textPrimary,
      )
      .copyWith(
        headlineMedium: const TextStyle(
          fontWeight: FontWeight.w700,
          letterSpacing: -0.5,
        ),
        headlineSmall: const TextStyle(fontWeight: FontWeight.w700),
        titleLarge: const TextStyle(fontWeight: FontWeight.w700),
        titleMedium: const TextStyle(fontWeight: FontWeight.w600),
      );

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.background,
    textTheme: textTheme,
    dividerColor: AppColors.outline,
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: AppColors.textPrimary,
        fontSize: 20,
        fontWeight: FontWeight.w700,
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surfaceHigh,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: AppRadius.borderMd),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surfaceHigh,
      hintStyle: const TextStyle(color: AppColors.textMuted),
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: AppRadius.borderMd,
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: AppRadius.borderMd,
        borderSide: const BorderSide(color: AppColors.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: AppRadius.borderMd,
        borderSide: const BorderSide(color: AppColors.primary, width: 1.6),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.borderMd),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: AppColors.textSecondary),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.textPrimary,
        side: const BorderSide(color: AppColors.outline),
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: AppRadius.borderMd),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      indicatorColor: AppColors.primary.withValues(alpha: 0.22),
      height: 68,
      labelTextStyle: WidgetStatePropertyAll(
        const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      ),
    ),
    navigationRailTheme: const NavigationRailThemeData(
      backgroundColor: AppColors.surface,
      indicatorColor: AppColors.primary,
      labelType: NavigationRailLabelType.all,
    ),
    chipTheme: ChipThemeData(
      backgroundColor: AppColors.surfaceHigh,
      selectedColor: AppColors.primary.withValues(alpha: 0.25),
      side: const BorderSide(color: AppColors.outline),
      shape: const StadiumBorder(),
      labelStyle: const TextStyle(color: AppColors.textSecondary),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.surfaceHighest,
      contentTextStyle: const TextStyle(color: AppColors.textPrimary),
      shape: RoundedRectangleBorder(borderRadius: AppRadius.borderMd),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surfaceHigh,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: AppRadius.borderLg),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.primary,
      linearTrackColor: AppColors.surfaceHighest,
    ),
    sliderTheme: const SliderThemeData(
      activeTrackColor: AppColors.primary,
      thumbColor: AppColors.primary,
      inactiveTrackColor: AppColors.surfaceHighest,
    ),
  );
}
