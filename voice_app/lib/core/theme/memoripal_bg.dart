import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../core/theme/app_theme.dart';

/// 메모리팔 앱 배경 - 딥 퍼플 밤하늘 + 별 + 달 + 구름
class MemoripalBackground extends StatelessWidget {
  final Widget child;
  final bool showClouds;
  final bool showMoon;

  const MemoripalBackground({
    super.key,
    required this.child,
    this.showClouds = true,
    this.showMoon = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(gradient: MemoColors.bgGradient),
      child: Stack(
        children: [
          // 별 파티클
          const _StarField(),
          // 달
          if (showMoon) const _MoonWidget(),
          // 핑크 구름 (하단)
          if (showClouds) const _CloudLayer(),
          // 실제 컨텐츠
          child,
        ],
      ),
    );
  }
}

// ── 별 필드 ──────────────────────────────────────────────
class _StarField extends StatelessWidget {
  const _StarField();

  static final List<_StarData> _stars = _generateStars();

  static List<_StarData> _generateStars() {
    final rng = Random(42); // 고정 시드로 일정한 별 위치
    return List.generate(35, (i) => _StarData(
      x: rng.nextDouble(),
      y: rng.nextDouble() * 0.75,
      size: rng.nextDouble() * 3 + 1.5,
      opacity: rng.nextDouble() * 0.5 + 0.3,
      delay: rng.nextInt(3000),
      isHeart: i % 8 == 0,
      isStar4: i % 5 == 0,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      return Stack(
        children: _stars.map((s) {
          final Widget icon = s.isHeart
              ? Text('♡', style: TextStyle(
                  color: MemoColors.lavenderLight.withOpacity(s.opacity * 0.6),
                  fontSize: s.size + 3,
                ))
              : s.isStar4
                  ? Text('✦', style: TextStyle(
                      color: MemoColors.starGold.withOpacity(s.opacity),
                      fontSize: s.size + 1,
                    ))
                  : Container(
                      width: s.size,
                      height: s.size,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(s.opacity),
                        shape: BoxShape.circle,
                      ),
                    );

          return Positioned(
            left: s.x * c.maxWidth,
            top: s.y * c.maxHeight,
            child: icon
                .animate(onPlay: (ctrl) => ctrl.repeat(reverse: true))
                .fadeIn(delay: Duration(milliseconds: s.delay), duration: 1500.ms)
                .then()
                .fadeOut(duration: 1500.ms),
          );
        }).toList(),
      );
    });
  }
}

class _StarData {
  final double x, y, size, opacity;
  final int delay;
  final bool isHeart, isStar4;
  const _StarData({
    required this.x, required this.y, required this.size,
    required this.opacity, required this.delay,
    required this.isHeart, required this.isStar4,
  });
}

// ── 달 ───────────────────────────────────────────────────
class _MoonWidget extends StatelessWidget {
  const _MoonWidget();

  @override
  Widget build(BuildContext context) {
    return Positioned(
      right: MediaQuery.of(context).size.width * 0.12,
      top: MediaQuery.of(context).size.height * 0.08,
      child: CustomPaint(
        size: const Size(50, 50),
        painter: _CrescentPainter(),
      )
          .animate()
          .fadeIn(delay: 300.ms, duration: 800.ms),
    );
  }
}

class _CrescentPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFFFE8A0)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    final glowPaint = Paint()
      ..color = const Color(0xFFFFE8A0).withOpacity(0.25)
      ..style = PaintingStyle.fill;

    // 초승달 모양
    final path = Path();
    path.addOval(Rect.fromCenter(
      center: Offset(size.width * 0.52, size.height * 0.5),
      width: size.width * 0.68,
      height: size.height * 0.68,
    ));
    canvas.drawPath(path, glowPaint);

    // 초승달 라인
    final arcRect = Rect.fromCenter(
      center: Offset(size.width * 0.5, size.height * 0.5),
      width: size.width * 0.72,
      height: size.height * 0.72,
    );
    canvas.drawArc(arcRect, -0.7, 3.5, false, paint);
  }

  @override
  bool shouldRepaint(_CrescentPainter old) => false;
}

// ── 핑크 구름 하단 ───────────────────────────────────────
class _CloudLayer extends StatelessWidget {
  const _CloudLayer();

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height;
    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      height: h * 0.22,
      child: CustomPaint(painter: _CloudPainter()),
    );
  }
}

class _CloudPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..style = PaintingStyle.fill;

    // 구름 그라데이션 (핑크)
    final gradient = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: [
        const Color(0xFFF4C5D0).withOpacity(0.0),
        const Color(0xFFF4C5D0).withOpacity(0.45),
        const Color(0xFFF4D8E4).withOpacity(0.55),
      ],
    );

    paint.shader = gradient.createShader(
      Rect.fromLTWH(0, 0, size.width, size.height),
    );

    final path = Path();
    path.moveTo(0, size.height * 0.55);
    // 물결 형태 구름 상단
    path.cubicTo(
      size.width * 0.1, size.height * 0.3,
      size.width * 0.2, size.height * 0.4,
      size.width * 0.3, size.height * 0.35,
    );
    path.cubicTo(
      size.width * 0.4, size.height * 0.3,
      size.width * 0.5, size.height * 0.5,
      size.width * 0.6, size.height * 0.38,
    );
    path.cubicTo(
      size.width * 0.75, size.height * 0.25,
      size.width * 0.88, size.height * 0.45,
      size.width, size.height * 0.4,
    );
    path.lineTo(size.width, size.height);
    path.lineTo(0, size.height);
    path.close();

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_CloudPainter old) => false;
}

/// 서브 배경 (핑크 그라데이션 - 서브 화면용)
class MemoSubBackground extends StatelessWidget {
  final Widget child;
  const MemoSubBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF2D1B69),
            Color(0xFF8B5BA8),
            Color(0xFFD4A8D8),
          ],
        ),
      ),
      child: child,
    );
  }
}