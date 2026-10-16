import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Album artwork with a graceful gradient/monogram fallback. Network images are
/// used only when the backend actually provides an artwork URL.
class Artwork extends StatelessWidget {
  const Artwork({
    super.key,
    this.url,
    this.size = 56,
    this.title,
    this.radius = AppRadius.sm,
    this.isPlaying = false,
  });

  final String? url;
  final double size;
  final String? title;
  final double radius;
  final bool isPlaying;

  @override
  Widget build(BuildContext context) {
    final hasUrl = url != null && url!.trim().isNotEmpty;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (hasUrl)
              Image.network(
                url!,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => _fallback(),
                loadingBuilder: (context, child, progress) {
                  if (progress == null) return child;
                  return _fallback();
                },
              )
            else
              _fallback(),
            if (isPlaying)
              Container(
                color: Colors.black.withValues(alpha: 0.45),
                child: Center(
                  child: EqualizerBars(size: size * 0.45),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _fallback() {
    final initial = (title ?? '?').trim().isEmpty
        ? '?'
        : (title!.trim()[0].toUpperCase());
    return Container(
      decoration: const BoxDecoration(gradient: AppColors.brandGradient),
      alignment: Alignment.center,
      child: Text(
        initial,
        style: TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w800,
          fontSize: size * 0.4,
        ),
      ),
    );
  }
}

/// Purely decorative equalizer currently used to signal an active/playing
/// track. It animates independently and never represents fake audio progress.
class EqualizerBars extends StatefulWidget {
  const EqualizerBars({super.key, this.size = 24, this.color = Colors.white});

  final double size;
  final Color color;

  @override
  State<EqualizerBars> createState() => _EqualizerBarsState();
}

class _EqualizerBarsState extends State<EqualizerBars>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const delays = [0.0, 0.35, 0.7, 0.2];
    return SizedBox(
      height: widget.size,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: List.generate(delays.length, (i) {
          return AnimatedBuilder(
            animation: _controller,
            builder: (context, _) {
              final t = (_controller.value + delays[i]) % 1.0;
              final scale = 0.35 + 0.65 * (t < 0.5 ? t * 2 : (1 - t) * 2);
              return Padding(
                padding: EdgeInsets.symmetric(horizontal: widget.size * 0.05),
                child: Container(
                  width: widget.size * 0.16,
                  height: widget.size * scale,
                  decoration: BoxDecoration(
                    color: widget.color,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              );
            },
          );
        }),
      ),
    );
  }
}
