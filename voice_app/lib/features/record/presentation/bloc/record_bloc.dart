import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:equatable/equatable.dart';
import '../../../../core/network/stt_service.dart';
import '../../../../core/network/llm_service.dart';
import '../../../../core/network/tts_service.dart';
import '../../domain/entities/memory.dart';

// --- Events ---
abstract class RecordEvent extends Equatable {
  const RecordEvent();
  @override
  List<Object?> get props => [];
}

class RecordStarted extends RecordEvent {}
class RecordStopped extends RecordEvent {}
class RecordCancelled extends RecordEvent {}
class RecordAmplitudeUpdated extends RecordEvent {
  final double amplitude;
  const RecordAmplitudeUpdated(this.amplitude);
  @override
  List<Object?> get props => [amplitude];
}
class RecordCategoryChanged extends RecordEvent {
  final MemoryCategory category;
  const RecordCategoryChanged(this.category);
  @override
  List<Object?> get props => [category];
}

// --- States ---
abstract class RecordState extends Equatable {
  const RecordState();
  @override
  List<Object?> get props => [];
}

class RecordIdle extends RecordState {}

class RecordInProgress extends RecordState {
  final Duration elapsed;
  final double amplitude;

  const RecordInProgress({
    required this.elapsed,
    required this.amplitude,
  });

  @override
  List<Object?> get props => [elapsed, amplitude];
}

class RecordProcessing extends RecordState {
  final ProcessingStep step;
  const RecordProcessing(this.step);
  @override
  List<Object?> get props => [step];
}

class RecordCompleted extends RecordState {
  final String transcript;
  final String summary;
  final String audioPath;
  final List<String> tags;
  final MemoryCategory category;

  const RecordCompleted({
    required this.transcript,
    required this.summary,
    required this.audioPath,
    required this.tags,
    required this.category,
  });

  @override
  List<Object?> get props => [transcript, summary, audioPath, tags, category];
}

class RecordError extends RecordState {
  final String message;
  const RecordError(this.message);
  @override
  List<Object?> get props => [message];
}

enum ProcessingStep { stt, summarizing, tagging, saving }

// --- BLoC ---
class RecordBloc extends Bloc<RecordEvent, RecordState> {
  final RecordingManager _recordingManager;
  final LlmService _llmService;
  final TtsService _ttsService;

  Timer? _elapsedTimer;
  StreamSubscription<double>? _amplitudeSub;
  Duration _elapsed = Duration.zero;
  MemoryCategory _selectedCategory = MemoryCategory.general;

  RecordBloc({
    required RecordingManager recordingManager,
    required LlmService llmService,
    required TtsService ttsService,
  })  : _recordingManager = recordingManager,
        _llmService = llmService,
        _ttsService = ttsService,
        super(RecordIdle()) {
    on<RecordStarted>(_onStarted);
    on<RecordStopped>(_onStopped);
    on<RecordCancelled>(_onCancelled);
    on<RecordAmplitudeUpdated>(_onAmplitudeUpdated);
    on<RecordCategoryChanged>(_onCategoryChanged);
  }

  Future<void> _onStarted(
    RecordStarted event,
    Emitter<RecordState> emit,
  ) async {
    try {
      await _recordingManager.startRecording();

      _elapsed = Duration.zero;
      _elapsedTimer?.cancel();
      _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        _elapsed += const Duration(seconds: 1);
        if (state is RecordInProgress) {
          add(RecordAmplitudeUpdated(
            (state as RecordInProgress).amplitude,
          ));
        }
      });

      _amplitudeSub?.cancel();
      _amplitudeSub = _recordingManager.amplitudeStream.listen((amp) {
        add(RecordAmplitudeUpdated(amp));
      });

      emit(const RecordInProgress(elapsed: Duration.zero, amplitude: 0.0));
    } catch (e) {
      emit(RecordError(e.toString()));
    }
  }

  Future<void> _onStopped(
    RecordStopped event,
    Emitter<RecordState> emit,
  ) async {
    _elapsedTimer?.cancel();
    _amplitudeSub?.cancel();

    try {
      // Step 1: STT
      emit(const RecordProcessing(ProcessingStep.stt));
      final result = await _recordingManager.stopAndTranscribe();
      final transcript = result.sttResult.transcript;

      // Step 2: LLM 요약
      emit(const RecordProcessing(ProcessingStep.summarizing));
      final summary = await _llmService.summarizeMemory(transcript);

      // Step 3: 태그 생성
      emit(const RecordProcessing(ProcessingStep.tagging));
      final tags = await _llmService.generateTags(transcript);

      emit(RecordCompleted(
        transcript: transcript,
        summary: summary,
        audioPath: result.audioPath,
        tags: tags,
        category: _selectedCategory,
      ));
    } catch (e) {
      emit(RecordError('처리 중 오류가 발생했습니다: $e'));
    }
  }

  Future<void> _onCancelled(
    RecordCancelled event,
    Emitter<RecordState> emit,
  ) async {
    _elapsedTimer?.cancel();
    _amplitudeSub?.cancel();
    await _recordingManager.cancelRecording();
    emit(RecordIdle());
  }

  void _onAmplitudeUpdated(
    RecordAmplitudeUpdated event,
    Emitter<RecordState> emit,
  ) {
    if (state is RecordInProgress) {
      emit(RecordInProgress(
        elapsed: _elapsed,
        amplitude: event.amplitude,
      ));
    }
  }

  void _onCategoryChanged(
    RecordCategoryChanged event,
    Emitter<RecordState> emit,
  ) {
    _selectedCategory = event.category;
  }

  @override
  Future<void> close() async {
    _elapsedTimer?.cancel();
    await _amplitudeSub?.cancel();
    await _recordingManager.dispose();
    return super.close();
  }
}
