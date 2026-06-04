import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/haptic_feedback.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../domain/entities/memory.dart';
import '../bloc/record_bloc.dart';
import '../widgets/waveform_visualizer.dart';
import '../widgets/processing_indicator.dart';

class RecordPage extends StatelessWidget {
  const RecordPage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<RecordBloc, RecordState>(
      listener: (context, state) {
        if (state is RecordCompleted) {
          _showSaveDialog(context, state);
        } else if (state is RecordError) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(state.message),
              backgroundColor: AppColors.error,
            ),
          );
        }
      },
      builder: (context, state) {
        return Scaffold(
          backgroundColor: AppColors.primary,
          body: SafeArea(
            child: _buildBody(context, state),
          ),
        );
      },
    );
  }

  Widget _buildBody(BuildContext context, RecordState state) {
    if (state is RecordProcessing) {
      return ProcessingIndicator(step: state.step);
    }

    if (state is RecordInProgress) {
      return _RecordingView(state: state);
    }

    return _IdleView();
  }

  void _showSaveDialog(BuildContext context, RecordCompleted state) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _SaveMemorySheet(state: state),
    );
  }
}

// --- 대기 화면 ---
class _IdleView extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _buildHeader(context),
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildCategorySelector(context),
              const SizedBox(height: 48),
              _buildRecordButton(context),
              const SizedBox(height: 24),
              Text(
                '버튼을 눌러 음성 메모를 시작하세요',
                style: Theme.of(context).textTheme.bodyMedium,
              ).animate().fadeIn(delay: 300.ms),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            '음성 메모',
            style: Theme.of(context).textTheme.displayMedium,
          ).animate().fadeInLeft(),
          IconButton(
            icon: const Icon(Icons.settings_outlined, color: AppColors.textSecondary),
            onPressed: () => Navigator.pushNamed(context, '/settings'),
          ),
        ],
      ),
    );
  }

  Widget _buildCategorySelector(BuildContext context) {
    return SizedBox(
      height: 48,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 24),
        itemCount: MemoryCategory.values.length,
        itemBuilder: (_, i) {
          final cat = MemoryCategory.values[i];
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: _CategoryChip(category: cat),
          );
        },
      ).animate().fadeIn(delay: 200.ms),
    );
  }

  Widget _buildRecordButton(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.heavyImpact();
        context.read<RecordBloc>().add(RecordStarted());
      },
      child: Container(
        width: 120,
        height: 120,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.accent, AppColors.secondary],
          ),
          boxShadow: [
            BoxShadow(
              color: AppColors.accent.withOpacity(0.4),
              blurRadius: 32,
              spreadRadius: 4,
            ),
          ],
        ),
        child: const Icon(
          Icons.mic_rounded,
          color: Colors.white,
          size: 48,
        ),
      )
          .animate(onPlay: (c) => c.repeat())
          .shimmer(duration: 2.seconds, color: Colors.white.withOpacity(0.2)),
    );
  }
}

// --- 녹음 중 화면 ---
class _RecordingView extends StatelessWidget {
  final RecordInProgress state;
  const _RecordingView({required this.state});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 40),
        _buildTimer(context),
        const SizedBox(height: 48),
        Expanded(
          child: WaveformVisualizer(amplitude: state.amplitude),
        ),
        _buildControls(context),
        const SizedBox(height: 48),
      ],
    );
  }

  Widget _buildTimer(BuildContext context) {
    final d = state.elapsed;
    final mm = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final ss = d.inSeconds.remainder(60).toString().padLeft(2, '0');

    return Column(
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: const BoxDecoration(
            color: AppColors.error,
            shape: BoxShape.circle,
          ),
        )
            .animate(onPlay: (c) => c.repeat())
            .fadeOut(duration: 700.ms)
            .then()
            .fadeIn(duration: 700.ms),
        const SizedBox(height: 16),
        Text(
          '$mm:$ss',
          style: const TextStyle(
            color: AppColors.textPrimary,
            fontSize: 56,
            fontWeight: FontWeight.w700,
            letterSpacing: -2,
            fontFamily: 'Pretendard',
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          '녹음 중',
          style: TextStyle(
            color: AppColors.accent,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildControls(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // 취소 버튼
        GestureDetector(
          onTap: () {
            HapticFeedback.mediumImpact();
            context.read<RecordBloc>().add(RecordCancelled());
          },
          child: Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.surfaceCard,
              border: Border.all(color: const Color(0xFF2A3F5F)),
            ),
            child: const Icon(Icons.close, color: AppColors.textSecondary, size: 28),
          ),
        ),
        const SizedBox(width: 32),
        // 중지 버튼
        GestureDetector(
          onTap: () {
            HapticFeedback.heavyImpact();
            context.read<RecordBloc>().add(RecordStopped());
          },
          child: Container(
            width: 88,
            height: 88,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.error,
              boxShadow: [
                BoxShadow(
                  color: AppColors.error.withOpacity(0.4),
                  blurRadius: 24,
                  spreadRadius: 4,
                ),
              ],
            ),
            child: Container(
              margin: const EdgeInsets.all(22),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(6),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// --- 카테고리 칩 ---
class _CategoryChip extends StatelessWidget {
  final MemoryCategory category;
  const _CategoryChip({required this.category});

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<RecordBloc, RecordState>(
      builder: (context, state) {
        return GestureDetector(
          onTap: () {
            context.read<RecordBloc>().add(RecordCategoryChanged(category));
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.surfaceCard,
              borderRadius: BorderRadius.circular(AppConstants.borderRadiusCircle),
              border: Border.all(color: const Color(0xFF2A3F5F)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(category.emoji, style: const TextStyle(fontSize: 16)),
                const SizedBox(width: 6),
                Text(
                  category.label,
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

// --- 저장 바텀시트 ---
class _SaveMemorySheet extends StatefulWidget {
  final RecordCompleted state;
  const _SaveMemorySheet({required this.state});

  @override
  State<_SaveMemorySheet> createState() => _SaveMemorySheetState();
}

class _SaveMemorySheetState extends State<_SaveMemorySheet> {
  late final TextEditingController _titleController;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(
      text: widget.state.summary.length > 30
          ? widget.state.summary.substring(0, 30)
          : widget.state.summary,
    );
  }

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceElevated,
        borderRadius: BorderRadius.circular(AppConstants.borderRadiusXL),
        border: Border.all(color: const Color(0xFF2A3F5F)),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          24, 24, 24,
          24 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 핸들
            Center(
              child: Container(
                width: 40, height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFF2A3F5F),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              '메모 저장',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 20),
            // 요약
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.accentGlow,
                borderRadius: BorderRadius.circular(AppConstants.borderRadiusMedium),
                border: Border.all(color: AppColors.accent.withOpacity(0.3)),
              ),
              child: Text(
                widget.state.summary,
                style: const TextStyle(
                  color: AppColors.textPrimary,
                  fontSize: 14,
                  height: 1.6,
                ),
              ),
            ),
            const SizedBox(height: 16),
            // 태그
            if (widget.state.tags.isNotEmpty) ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: widget.state.tags.map((tag) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryGlow,
                    borderRadius: BorderRadius.circular(AppConstants.borderRadiusCircle),
                    border: Border.all(color: AppColors.secondary.withOpacity(0.4)),
                  ),
                  child: Text(
                    '#$tag',
                    style: const TextStyle(
                      color: AppColors.secondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                )).toList(),
              ),
              const SizedBox(height: 16),
            ],
            // 저장 버튼
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _isSaving ? null : _save,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.primary,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppConstants.borderRadiusLarge),
                  ),
                ),
                child: _isSaving
                    ? const SizedBox(
                        width: 20, height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2, color: AppColors.primary,
                        ),
                      )
                    : const Text(
                        '저장',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 16,
                        ),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _save() {
    setState(() => _isSaving = true);
    // TODO: MemoryBloc으로 저장 이벤트 발송
    Navigator.pop(context);
  }
}
