import 'dart:math';
import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';

/// 실시간 음성 파형 시각화 위젯
class WaveformVisualizer extends StatefulWidget {
  final double amplitude; // 0.0 ~ 1.0
  final int barCount;
  final Color activeColor;
  final Color inactiveColor;

  const WaveformVisualizer({
    super.key,
    required this.amplitude,
    this.barCount = 40,
    this.activeColor = AppColors.waveformActive,
    this.inactiveColor = AppColors.waveformInactive,
  });

  @override
  State<WaveformVisualizer> createState() => _WaveformVisualizerState();
}

class _WaveformVisualizerState extends State<WaveformVisualizer>
    with TickerProviderStateMixin {
  late AnimationController _controller;
  final List<double> _history = [];
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 50),
    )..addListener(() => setState(() {}));
    _controller.repeat();
  }

  @override
  void didUpdateWidget(WaveformVisualizer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.amplitude != widget.amplitude) {
      _history.add(widget.amplitude);
      if (_history.length > widget.barCount) {
        _history.removeAt(0);
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final maxHeight = constraints.maxHeight * 0.7;
          final barWidth = (constraints.maxWidth - (widget.barCount - 1) * 4) /
              widget.barCount;

          return Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: List.generate(widget.barCount, (i) {
                double barHeight;

                if (i < _history.length) {
                  final historyIndex = _history.length - widget.barCount + i;
                  if (historyIndex >= 0 && historyIndex < _history.length) {
                    barHeight = _history[historyIndex] * maxHeight;
                    // 최소 높이 보장 + 약간의 노이즈
                    barHeight = max(4, barHeight + _random.nextDouble() * 4);
                  } else {
                    barHeight = 4 + _random.nextDouble() * 8;
                  }
                } else {
                  barHeight = 4 + _random.nextDouble() * 8;
                }

                // 마지막 바 (현재 입력) 강조
                final isLatest = i == widget.barCount - 1;
                final progress = i / widget.barCount;

                return Container(
                  width: barWidth,
                  height: barHeight,
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(barWidth / 2),
                    gradient: isLatest
                        ? const LinearGradient(
                            begin: Alignment.bottomCenter,
                            end: Alignment.topCenter,
                            colors: [AppColors.accent, AppColors.secondary],
                          )
                        : LinearGradient(
                            begin: Alignment.bottomCenter,
                            end: Alignment.topCenter,
                            colors: [
                              AppColors.accent.withOpacity(0.2 + progress * 0.6),
                              AppColors.secondary.withOpacity(0.1 + progress * 0.4),
                            ],
                          ),
                  ),
                );
              }),
            ),
          );
        },
      ),
    );
  }
}

/// 재생 전용 파형 (정적 표시)
class StaticWaveform extends StatelessWidget {
  final List<double> waveData;
  final double progress; // 0.0 ~ 1.0 재생 진행도
  final Color playedColor;
  final Color unplayedColor;

  const StaticWaveform({
    super.key,
    required this.waveData,
    required this.progress,
    this.playedColor = AppColors.accent,
    this.unplayedColor = AppColors.waveformInactive,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final playedWidth = constraints.maxWidth * progress;

        return CustomPaint(
          size: Size(constraints.maxWidth, constraints.maxHeight),
          painter: _StaticWaveformPainter(
            waveData: waveData,
            playedWidth: playedWidth,
            playedColor: playedColor,
            unplayedColor: unplayedColor,
          ),
        );
      },
    );
  }
}

class _StaticWaveformPainter extends CustomPainter {
  final List<double> waveData;
  final double playedWidth;
  final Color playedColor;
  final Color unplayedColor;

  _StaticWaveformPainter({
    required this.waveData,
    required this.playedWidth,
    required this.playedColor,
    required this.unplayedColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (waveData.isEmpty) return;

    final barWidth = size.width / waveData.length;
    final centerY = size.height / 2;

    for (var i = 0; i < waveData.length; i++) {
      final x = i * barWidth + barWidth / 2;
      final barHeight = max(2.0, waveData[i] * size.height);
      final isPlayed = x <= playedWidth;

      final paint = Paint()
        ..color = isPlayed ? playedColor : unplayedColor
        ..strokeCap = StrokeCap.round
        ..strokeWidth = max(1, barWidth - 2);

      canvas.drawLine(
        Offset(x, centerY - barHeight / 2),
        Offset(x, centerY + barHeight / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_StaticWaveformPainter old) =>
      old.playedWidth != playedWidth || old.waveData != waveData;
}
