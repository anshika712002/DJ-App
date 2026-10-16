/// Small presentation-only formatting helpers.
String formatDuration(int? seconds) {
  if (seconds == null || seconds <= 0) return '';
  final m = seconds ~/ 60;
  final s = seconds % 60;
  return '$m:${s.toString().padLeft(2, '0')}';
}

String sourceLabel(String sourceType) {
  switch (sourceType) {
    case 'youtube':
      return 'YouTube';
    case 'local':
      return 'Local upload';
    case 'licensed':
      return 'Licensed';
    case 'public_domain':
      return 'Public domain';
    default:
      return sourceType;
  }
}
