import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../core/constants/app_constants.dart';
import '../../features/chat/domain/entities/chat_message.dart';
import '../../features/memory/domain/entities/memory.dart';

/// LLM 응답 청크 (스트리밍)
class LlmChunk {
  final String delta;
  final bool isDone;
  final List<String>? referencedMemoryIds;
  final Map<String, dynamic>? metadata;

  const LlmChunk({
    required this.delta,
    this.isDone = false,
    this.referencedMemoryIds,
    this.metadata,
  });
}

/// LLM 요청 컨텍스트
class LlmRequest {
  final String userMessage;
  final List<ChatMessage> history;
  final List<Memory> relevantMemories; // RAG 컨텍스트
  final String? systemPrompt;

  const LlmRequest({
    required this.userMessage,
    this.history = const [],
    this.relevantMemories = const [],
    this.systemPrompt,
  });

  Map<String, dynamic> toJson() => {
    'message': userMessage,
    'history': history.map((m) => {
      'role': m.role.name,
      'content': m.content,
    }).toList(),
    'context': relevantMemories.map((m) => {
      'id': m.id,
      'summary': m.summary,
      'tags': m.tags,
      'created_at': m.createdAt.toIso8601String(),
    }).toList(),
    if (systemPrompt != null) 'system_prompt': systemPrompt,
  };
}

/// LLM 서비스
class LlmService {
  final Dio _dio;
  WebSocketChannel? _wsChannel;

  LlmService({Dio? dio})
      : _dio = dio ?? Dio(BaseOptions(baseUrl: AppConstants.baseUrl));

  /// 스트리밍 채팅 응답 (SSE 방식)
  Stream<LlmChunk> streamChat(LlmRequest request) async* {
    final controller = StreamController<LlmChunk>();

    _dio
        .post(
      AppConstants.llmStreamEndpoint,
      data: request.toJson(),
      options: Options(
        responseType: ResponseType.stream,
        headers: {'Accept': 'text/event-stream'},
      ),
    )
        .then((response) async {
      await for (final chunk
          in (response.data as ResponseBody).stream) {
        final lines = utf8.decode(chunk).split('\n');
        for (final line in lines) {
          if (line.startsWith('data: ')) {
            final jsonStr = line.substring(6).trim();
            if (jsonStr == '[DONE]') {
              controller.add(const LlmChunk(delta: '', isDone: true));
              await controller.close();
              return;
            }
            try {
              final data = jsonDecode(jsonStr) as Map<String, dynamic>;
              controller.add(LlmChunk(
                delta: data['delta'] as String? ?? '',
                isDone: data['done'] as bool? ?? false,
                referencedMemoryIds:
                    (data['referenced_memories'] as List<dynamic>?)
                        ?.cast<String>(),
              ));
            } catch (_) {
              // 파싱 오류 무시
            }
          }
        }
      }
    }).catchError((e) {
      controller.addError(LlmException('LLM 스트리밍 오류: $e', e));
      controller.close();
    });

    yield* controller.stream;
  }

  /// 단일 응답 (비스트리밍)
  Future<String> chat(LlmRequest request) async {
    try {
      final response = await _dio.post(
        AppConstants.llmEndpoint,
        data: request.toJson(),
        options: Options(
          sendTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 60),
        ),
      );
      return (response.data as Map<String, dynamic>)['response'] as String;
    } on DioException catch (e) {
      throw LlmException('LLM 요청 실패: ${e.message}', e);
    }
  }

  /// 메모리 요약 생성
  Future<String> summarizeMemory(String transcript) async {
    try {
      final response = await _dio.post(
        '/llm/summarize',
        data: {
          'text': transcript,
          'language': 'ko',
          'max_length': 200,
        },
      );
      return (response.data as Map<String, dynamic>)['summary'] as String;
    } on DioException catch (e) {
      throw LlmException('요약 생성 실패: ${e.message}', e);
    }
  }

  /// 메모리 태그 자동 생성
  Future<List<String>> generateTags(String transcript) async {
    try {
      final response = await _dio.post(
        '/llm/tags',
        data: {'text': transcript, 'max_tags': 5},
      );
      return ((response.data as Map<String, dynamic>)['tags'] as List)
          .cast<String>();
    } on DioException catch (e) {
      throw LlmException('태그 생성 실패: ${e.message}', e);
    }
  }

  /// 관련 메모리 검색 (Semantic Search)
  Future<List<String>> findRelatedMemories(String query) async {
    try {
      final response = await _dio.post(
        '/memories/search',
        data: {'query': query, 'top_k': 5},
      );
      return ((response.data as Map<String, dynamic>)['ids'] as List)
          .cast<String>();
    } on DioException catch (e) {
      throw LlmException('메모리 검색 실패: ${e.message}', e);
    }
  }

  void dispose() {
    _wsChannel?.sink.close();
    _dio.close();
  }
}

/// 엔드투엔드 파이프라인 (STT → LLM → TTS) WebSocket
class PipelineService {
  WebSocketChannel? _channel;
  final _responseController = StreamController<PipelineEvent>.broadcast();

  Stream<PipelineEvent> get events => _responseController.stream;

  Future<void> connect() async {
    _channel = WebSocketChannel.connect(
      Uri.parse('${AppConstants.wsBaseUrl}${AppConstants.wsEndpoint}'),
    );

    _channel!.stream.listen(
      (data) {
        final json = jsonDecode(data as String) as Map<String, dynamic>;
        _responseController.add(PipelineEvent.fromJson(json));
      },
      onError: (e) => _responseController.addError(e),
      onDone: () => _responseController.add(const PipelineEvent.disconnected()),
    );
  }

  /// 음성 데이터 전송 (청크 단위)
  void sendAudioChunk(List<int> audioData) {
    _channel?.sink.add(jsonEncode({
      'type': 'audio_chunk',
      'data': base64Encode(audioData),
    }));
  }

  /// 녹음 완료 신호
  void sendEndOfSpeech() {
    _channel?.sink.add(jsonEncode({'type': 'end_of_speech'}));
  }

  Future<void> disconnect() async {
    await _channel?.sink.close();
    _channel = null;
  }

  void dispose() {
    disconnect();
    _responseController.close();
  }
}

/// 파이프라인 이벤트 타입
class PipelineEvent {
  final PipelineEventType type;
  final String? transcript;    // STT 결과
  final String? llmDelta;      // LLM 스트리밍 텍스트
  final String? ttsAudioB64;   // TTS 오디오 (base64)
  final String? error;

  const PipelineEvent({
    required this.type,
    this.transcript,
    this.llmDelta,
    this.ttsAudioB64,
    this.error,
  });

  const PipelineEvent.disconnected()
      : type = PipelineEventType.disconnected,
        transcript = null,
        llmDelta = null,
        ttsAudioB64 = null,
        error = null;

  factory PipelineEvent.fromJson(Map<String, dynamic> json) {
    final typeStr = json['type'] as String;
    return PipelineEvent(
      type: PipelineEventType.values.firstWhere(
        (e) => e.name == typeStr,
        orElse: () => PipelineEventType.unknown,
      ),
      transcript: json['transcript'] as String?,
      llmDelta: json['delta'] as String?,
      ttsAudioB64: json['audio'] as String?,
      error: json['error'] as String?,
    );
  }
}

enum PipelineEventType {
  sttPartial,
  sttFinal,
  llmStart,
  llmDelta,
  llmEnd,
  ttsChunk,
  ttsDone,
  disconnected,
  unknown,
  error,
}

class LlmException implements Exception {
  final String message;
  final Object? cause;
  LlmException(this.message, [this.cause]);
  @override
  String toString() => 'LlmException: $message';
}
