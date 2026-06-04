import 'dart:async';
import 'dart:io';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';
import 'package:dio/dio.dart';
import '../../core/constants/app_constants.dart';

/// STT 결과 모델
class SttResult {
  final String transcript;
  final double confidence;
  final bool isFinal;
  final Duration? processingTime;

  const SttResult({
    required this.transcript,
    required this.confidence,
    this.isFinal = true,
    this.processingTime,
  });
}

/// STT 서비스 추상 인터페이스
abstract class SttService {
  Future<SttResult> transcribeFile(String audioPath);
  Stream<SttResult> transcribeStream(Stream<List<int>> audioStream);
  Future<void> dispose();
}

/// 네이티브 STT 서비스 (기기 자체 STT 활용)
/// 우선적으로 사용; 정확도 개선 후 CustomSttService로 교체
class NativeSttService implements SttService {
  final Dio _dio;

  NativeSttService({Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: AppConstants.baseUrl));

  @override
  Future<SttResult> transcribeFile(String audioPath) async {
    final stopwatch = Stopwatch()..start();

    try {
      final formData = FormData.fromMap({
        'audio': await MultipartFile.fromFile(
          audioPath,
          filename: 'audio.m4a',
        ),
        'language': 'ko',         // 한국어 우선
        'mode': AppConstants.sttModeNative,
      });

      final response = await _dio.post(
        AppConstants.sttEndpoint,
        data: formData,
        options: Options(
          headers: {'Content-Type': 'multipart/form-data'},
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 60),
        ),
      );

      stopwatch.stop();
      final data = response.data as Map<String, dynamic>;

      return SttResult(
        transcript: data['transcript'] as String,
        confidence: (data['confidence'] as num?)?.toDouble() ?? 0.9,
        isFinal: true,
        processingTime: stopwatch.elapsed,
      );
    } on DioException catch (e) {
      throw SttException('STT 처리 실패: ${e.message}', e);
    }
  }

  @override
  Stream<SttResult> transcribeStream(Stream<List<int>> audioStream) async* {
    // 실시간 스트리밍 STT: WebSocket 연결로 구현
    // TODO: WebSocket 스트리밍 구현
    yield SttResult(
      transcript: '',
      confidence: 0.0,
      isFinal: false,
    );
  }

  @override
  Future<void> dispose() async {
    _dio.close();
  }
}

/// 자체 개발 STT 서비스 (고정밀도 모드)
/// NativeSttService 정확도 한계 도달 시 교체
class CustomSttService implements SttService {
  final Dio _dio;

  CustomSttService({Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: AppConstants.baseUrl));

  @override
  Future<SttResult> transcribeFile(String audioPath) async {
    final stopwatch = Stopwatch()..start();

    try {
      final formData = FormData.fromMap({
        'audio': await MultipartFile.fromFile(
          audioPath,
          filename: 'audio.wav',
        ),
        'language': 'ko',
        'mode': AppConstants.sttModeCustom,
        'beam_size': 5,           // Beam search 크기
        'word_timestamps': true,  // 단어별 타임스탬프
      });

      final response = await _dio.post(
        AppConstants.sttEndpoint,
        data: formData,
      );

      stopwatch.stop();
      final data = response.data as Map<String, dynamic>;

      return SttResult(
        transcript: data['transcript'] as String,
        confidence: (data['confidence'] as num?)?.toDouble() ?? 0.95,
        isFinal: true,
        processingTime: stopwatch.elapsed,
      );
    } on DioException catch (e) {
      throw SttException('Custom STT 처리 실패: ${e.message}', e);
    }
  }

  @override
  Stream<SttResult> transcribeStream(Stream<List<int>> audioStream) async* {
    // 청크 단위로 음성 데이터를 받아 실시간 변환
    await for (final chunk in audioStream) {
      // TODO: WebSocket 스트리밍 구현
      yield SttResult(
        transcript: '',
        confidence: 0.0,
        isFinal: false,
      );
    }
  }

  @override
  Future<void> dispose() async {
    _dio.close();
  }
}

/// 녹음 관리자 - 녹음 + STT 파이프라인 통합
class RecordingManager {
  final AudioRecorder _recorder = AudioRecorder();
  final SttService _sttService;
  
  String? _currentRecordPath;
  bool _isRecording = false;
  Timer? _amplitudeTimer;

  final _amplitudeController = StreamController<double>.broadcast();
  Stream<double> get amplitudeStream => _amplitudeController.stream;

  RecordingManager({SttService? sttService})
      : _sttService = sttService ?? NativeSttService();

  bool get isRecording => _isRecording;

  /// 녹음 시작
  Future<void> startRecording() async {
    if (!await _recorder.hasPermission()) {
      throw RecordingException('마이크 권한이 없습니다');
    }

    final dir = await getApplicationDocumentsDirectory();
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    _currentRecordPath = '${dir.path}/recording_$timestamp.m4a';

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: AppConstants.sampleRate,
        numChannels: AppConstants.channels,
        bitRate: AppConstants.bitRate,
      ),
      path: _currentRecordPath!,
    );

    _isRecording = true;
    _startAmplitudeMonitoring();
  }

  /// 녹음 중지 및 STT 처리
  Future<({String audioPath, SttResult sttResult})> stopAndTranscribe() async {
    if (!_isRecording) throw RecordingException('녹음 중이 아닙니다');

    _amplitudeTimer?.cancel();
    final audioPath = await _recorder.stop();
    _isRecording = false;

    if (audioPath == null) throw RecordingException('오디오 파일 생성 실패');

    final sttResult = await _sttService.transcribeFile(audioPath);
    return (audioPath: audioPath, sttResult: sttResult);
  }

  /// 녹음 취소
  Future<void> cancelRecording() async {
    _amplitudeTimer?.cancel();
    await _recorder.stop();
    _isRecording = false;
    
    // 임시 파일 삭제
    if (_currentRecordPath != null) {
      final file = File(_currentRecordPath!);
      if (await file.exists()) await file.delete();
    }
  }

  void _startAmplitudeMonitoring() {
    _amplitudeTimer = Timer.periodic(
      const Duration(milliseconds: 50),
      (_) async {
        if (_isRecording) {
          final amp = await _recorder.getAmplitude();
          // -160dB(무음) ~ 0dB(최대) → 0.0 ~ 1.0 정규화
          final normalized = ((amp.current + 60) / 60).clamp(0.0, 1.0);
          _amplitudeController.add(normalized);
        }
      },
    );
  }

  Future<void> dispose() async {
    _amplitudeTimer?.cancel();
    await _amplitudeController.close();
    await _recorder.dispose();
    await _sttService.dispose();
  }
}

class SttException implements Exception {
  final String message;
  final Object? cause;
  SttException(this.message, [this.cause]);
  @override
  String toString() => 'SttException: $message';
}

class RecordingException implements Exception {
  final String message;
  RecordingException(this.message);
  @override
  String toString() => 'RecordingException: $message';
}
