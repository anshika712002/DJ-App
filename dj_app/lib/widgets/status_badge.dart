import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Rounded pill that shows a request/song status with its theme colour + icon.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.status, this.dense = false});

  final String status;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final visual = statusVisual(status);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: dense ? 9 : 12,
        vertical: dense ? 4 : 6,
      ),
      decoration: BoxDecoration(
        color: visual.color.withValues(alpha: 0.16),
        border: Border.all(color: visual.color.withValues(alpha: 0.65)),
        borderRadius: AppRadius.borderPill,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(visual.icon, size: dense ? 12 : 14, color: visual.color),
          const SizedBox(width: 6),
          Text(
            visual.label,
            style: TextStyle(
              color: visual.color,
              fontSize: dense ? 11 : 12.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }
}
