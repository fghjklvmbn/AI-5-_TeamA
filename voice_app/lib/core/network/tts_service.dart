import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import '../../core/constants/app_constants.dart';

class TtsService {
  final Dio _dio;
  final AudioPlayer _player = AudioPlayer();

  TtsService({Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: AppConstants.baseUrl));

  bool get isPlaying => _player.playing;
  Stream<PlayerState> get playerStateStream => _player.playerStateStream;
  Stream<Duration?> get durationStream => _player.durationStream;
  Stream<Duration> get positionStream => _player.positionStream;

  /// 텍스트를 음성으로 변환 후 즉시 재생
  Future<String> synthesizeAndPlay(String text, {
    String voice = 'ko_female_1',
    double speed = 1.0,
    double pitch = 1.0,
  }) async {
    final audioPath = await synthesize(
      text,
      voice: voice,
      speed: speed,
      pitch: pitch,
    );
    await play(audioPath);
    return audioPath;
  }

  /// 텍스트 → 오디오 파일 변환
  Future<String> synthesize(String text, {
    String voice = 'ko_female_1',
    double speed = 1.0,
    double pitch = 1.0,
  }) async {
    try {
      final response = await _dio.post(
        AppConstants.ttsEndpoint,
        data: {
          'text': text,
          'voice': voice,
          'speed': speed,
          'pitch': pitch,
          'format': 'wav',
          'sample_rate': 22050,
        },
        options: Options(
          responseType: ResponseType.bytes,
          receiveTimeout: const Duration(seconds: 30),
        ),
      );

      final dir = await getTemporaryDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final audioPath = '${dir.path}/tts_$timestamp.wav';
      final file = File(audioPath);
      await file.writeAsBytes(response.data as List<int>);

      return audioPath;
    } on DioException catch (e) {
      throw TtsException('TTS 변환 실패: ${e.message}', e);
    }
  }

  /// 스트리밍 TTS 재생 (실시간)
  Stream<Uint8List> synthesizeStream(String text, {
    String voice = 'ko_female_1',
    double speed = 1.0,
  }) async* {
    try {
      final response = await _dio.post(
        '/tts/stream',
        data: {'text': text, 'voice': voice, 'speed': speed},
        options: Options(responseType: ResponseType.stream),
      );

      await for (final chunk
          in (response.data as ResponseBody).stream) {
        yield Uint8List.fromList(chunk);
      }
    } on DioException catch (e) {
      throw TtsException('TTS 스트리밍 실패: ${e.message}', e);
    }
  }

  /// 오디오 파일 재생
  Future<void> play(String audioPath) async {
    await _player.setFilePath(audioPath);
    await _player.play();
  }

  Future<void> pause() async => _player.pause();
  Future<void> resume() async => _player.play();
  Future<void> stop() async => _player.stop();

  Future<void> seek(Duration position) async => _player.seek(position);

  Future<void> setSpeed(double speed) async => _player.setSpeed(speed);

  Future<void> dispose() async {
    await _player.dispose();
    _dio.close();
  }
}

class TtsException implements Exception {
  final String message;
  final Object? cause;
  TtsException(this.message, [this.cause]);
  @override
  String toString() => 'TtsException: $message';
}
