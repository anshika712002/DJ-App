import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// On wide windows the app is presented in a compact, phone-style frame instead
/// of stretching into a web dashboard. The inner MediaQuery reports the frame
/// size so every screen lays out like a mobile app.
class MobileFrame extends StatelessWidget {
  const MobileFrame({super.key, required this.child, this.maxWidth = 460});

  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    if (media.size.width < 640 || media.size.height < 500) return child;

    final height = (media.size.height - 48).clamp(480.0, 900.0).toDouble();
    final frameSize = Size(maxWidth, height);

    return ColoredBox(
      color: const Color(0xFF05050A),
      child: Center(
        child: Container(
          width: frameSize.width,
          height: frameSize.height,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.circular(34),
            border: Border.all(color: AppColors.outline, width: 1.5),
            boxShadow: const [
              BoxShadow(
                color: Colors.black,
                blurRadius: 42,
                spreadRadius: 4,
                offset: Offset(0, 14),
              ),
            ],
          ),
          child: MediaQuery(
            data: media.copyWith(size: frameSize),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// Centers content and caps its width so desktop windows do not stretch lists
/// across the whole screen while phones keep full-width layouts.
class ConstrainedContent extends StatelessWidget {
  const ConstrainedContent({
    super.key,
    required this.child,
    this.maxWidth = 920,
    this.padding = EdgeInsets.zero,
  });

  final Widget child;
  final double maxWidth;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}
