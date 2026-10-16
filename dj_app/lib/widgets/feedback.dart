import 'package:flutter/material.dart';

import '../src/api_client.dart';
import '../theme/app_theme.dart';

/// Shows a friendly, non-blocking error message. Diagnostic detail stays in the
/// exception message; nothing sensitive is rendered.
void showApiError(BuildContext context, Object error) {
  final message = error is ApiException ? error.message : error.toString();
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Row(
        children: [
          const Icon(Icons.error_outline, color: AppColors.danger),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
      backgroundColor: AppColors.surfaceHighest,
      behavior: SnackBarBehavior.floating,
    ),
  );
}

void showInfo(BuildContext context, String message) {
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(message),
      behavior: SnackBarBehavior.floating,
    ),
  );
}

/// Confirmation dialog for destructive/consequential DJ actions.
Future<bool> confirmAction(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'Confirm',
  bool destructive = false,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: destructive
              ? FilledButton.styleFrom(backgroundColor: AppColors.danger)
              : null,
          onPressed: () => Navigator.of(context).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}
