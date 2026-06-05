import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Memoripal 색상 팔레트 - 딥 퍼플 나이트 테마
class MemoColors {
  MemoColors._();

  // ── Background ──────────────────────────────
  static const Color bgDark    = Color(0xFF0D0925);  // 최심 퍼플-네이비
  static const Color bgMid     = Color(0xFF1E1050);  // 다크 퍼플
  static const Color bgLight   = Color(0xFF2D1B69);  // 미디엄 퍼플
  static const Color bgPink    = Color(0xFFF4C5D0);  // 핑크 클라우드

  // ── Surface / Card ───────────────────────────
  static const Color surface       = Color(0xFF150C38);
  static const Color surfaceCard   = Color(0xFF1E1248);
  static const Color surfaceLight  = Color(0xFF271558);
  static const Color cardBorder    = Color(0xFF3D2A70);

  // ── Lavender Accent ──────────────────────────
  static const Color lavender      = Color(0xFF9B7FD4);
  static const Color lavenderLight = Color(0xFFC4A8E8);
  static const Color lavenderDeep  = Color(0xFF6B4FA0);
  static const Color lavenderGlow  = Color(0x409B7FD4);

  // ── Pink ─────────────────────────────────────
  static const Color pink      = Color(0xFFE8A8C4);
  static const Color pinkLight = Color(0xFFF4C5D0);
  static const Color pinkGlow  = Color(0x40E8A8C4);

  // ── Star & Moon ──────────────────────────────
  static const Color starGold  = Color(0xFFF5C842);
  static const Color moonCream = Color(0xFFFFE8A0);

  // ── Text ─────────────────────────────────────
  static const Color textPrimary   = Color(0xFFF0E8FF);
  static const Color textSecondary = Color(0xFFB8A8D8);
  static const Color textTertiary  = Color(0xFF6B5B8A);

  // ── Semantic ─────────────────────────────────
  static const Color success = Color(0xFF7DD4B5);
  static const Color error   = Color(0xFFE87E9B);
  static const Color warning = Color(0xFFFFB547);

  // ── Gradients ────────────────────────────────
  static const LinearGradient bgGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFF0D0925), Color(0xFF1E1050), Color(0xFF2D1B69)],
    stops: [0.0, 0.55, 1.0],
  );

  static const LinearGradient lavenderGrad = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF9B7FD4), Color(0xFFE8A8C4)],
  );

  static const LinearGradient recordBtnGrad = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF7B5EA7), Color(0xFF9B7FD4), Color(0xFFE8A8C4)],
  );

  static const LinearGradient pinkSkyGrad = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [Color(0xFFD4B8E8), Color(0xFFF4C5D0)],
  );
}

/// Memoripal 테마 설정
class MemoTheme {
  MemoTheme._();

  static ThemeData get dark {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      fontFamily: 'Pretendard',
      colorScheme: ColorScheme.dark(
        primary: MemoColors.lavender,
        onPrimary: MemoColors.bgDark,
        secondary: MemoColors.pink,
        surface: MemoColors.surface,
        onSurface: MemoColors.textPrimary,
        error: MemoColors.error,
      ),
      scaffoldBackgroundColor: MemoColors.bgDark,

      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        systemOverlayStyle: SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.light,
        ),
        titleTextStyle: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 17,
          fontWeight: FontWeight.w600,
          fontFamily: 'Pretendard',
        ),
        iconTheme: IconThemeData(color: MemoColors.textSecondary, size: 22),
      ),

      cardTheme: CardTheme(
        color: MemoColors.surfaceCard,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: MemoColors.cardBorder, width: 1),
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: MemoColors.surfaceLight,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: MemoColors.cardBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: MemoColors.cardBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: MemoColors.lavender, width: 1.5),
        ),
        hintStyle: const TextStyle(color: MemoColors.textTertiary, fontSize: 14),
        labelStyle: const TextStyle(color: MemoColors.textSecondary),
      ),

      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: MemoColors.lavender,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            fontFamily: 'Pretendard',
          ),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: MemoColors.lavender,
          side: const BorderSide(color: MemoColors.lavender),
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
      ),

      textTheme: const TextTheme(
        displayLarge: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 32,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.5,
        ),
        displayMedium: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 26,
          fontWeight: FontWeight.w700,
        ),
        titleLarge: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
        titleMedium: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w600,
        ),
        bodyLarge: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 15,
          fontWeight: FontWeight.w400,
          height: 1.6,
        ),
        bodyMedium: TextStyle(
          color: MemoColors.textSecondary,
          fontSize: 14,
          fontWeight: FontWeight.w400,
          height: 1.5,
        ),
        bodySmall: TextStyle(
          color: MemoColors.textTertiary,
          fontSize: 12,
        ),
        labelLarge: TextStyle(
          color: MemoColors.textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w500,
        ),
      ),

      listTileTheme: const ListTileThemeData(
        iconColor: MemoColors.lavender,
        textColor: MemoColors.textPrimary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(12)),
        ),
      ),

      sliderTheme: const SliderThemeData(
        activeTrackColor: MemoColors.lavender,
        inactiveTrackColor: MemoColors.cardBorder,
        thumbColor: MemoColors.lavender,
        overlayColor: MemoColors.lavenderGlow,
        valueIndicatorColor: MemoColors.lavenderDeep,
      ),

      dividerTheme: const DividerThemeData(
        color: MemoColors.cardBorder,
        thickness: 1,
        space: 0,
      ),
    );
  }
}

/// 텍스트 스타일 확장
extension MemoTextStyles on BuildContext {
  TextStyle get logoStyle => const TextStyle(
    color: MemoColors.lavenderLight,
    fontSize: 36,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.5,
    fontFamily: 'Pretendard',
  );
}