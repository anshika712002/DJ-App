import 'package:flutter/material.dart';

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
