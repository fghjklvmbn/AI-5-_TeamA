/// Memoripal 앱 전역 상수
class AppConst {
  AppConst._();

  // ── API ────────────────────────────────────────
  static const String baseUrl   = 'http://localhost:8000';
  static const String wsBaseUrl = 'ws://localhost:8000';

  static const String pingEndpoint     = '/ping';
  static const String sttEndpoint      = '/stt/transcribe';
  static const String llmEndpoint      = '/llm/chat';
  static const String llmStreamUrl     = '/llm/stream';
  static const String ttsEndpoint      = '/tts/synthesize';
  static const String ttsStreamUrl     = '/tts/stream';
  static const String voiceAddEndpoint = '/voices/add';
  static const String voiceListUrl     = '/voices';
  static const String pipelineWs      = '/ws/pipeline';
  static const String chatEndpoint     = '/chats';

  // ── 녹음 설정 (UD-401: 22050Hz, 모노) ──────────
  static const int sampleRate  = 22050;
  static const int channels    = 1;
  static const int bitRate     = 128000;
  static const int maxRecordSec = 7200; // 최대 2시간 (UD-102)

  // ── 음성 관리 제한 (UD-102) ────────────────────
  static const int maxVoiceProfiles  = 3;  // 최대 3개 음성 등록
  static const int maxClipsPerVoice  = 10; // 음성당 최대 10개 녹음
  static const int maxTotalSeconds   = 7200; // 총 2시간

  // ── TTS 기본 설정 ────────────────────────────────
  static const String defaultVoice = 'sohee'; // 기본 음성
  static const double pitchDefault = 1.0;
  static const double pitchMin     = 0.5;
  static const double pitchMax     = 3.0;
  static const double toneDefault  = 1.0;
  static const double toneMin      = 0.5;
  static const double toneMax      = 3.0;

  // ── SharedPreferences Keys ───────────────────────
  static const String keyUserId       = 'user_id';
  static const String keyUserEmail    = 'user_email';
  static const String keyPitch        = 'tts_pitch';
  static const String keyTone         = 'tts_tone';
  static const String keySelectedMode = 'record_mode';
  static const String keyServerUrl    = 'server_url';
  static const String keyVoiceCount   = 'voice_count';
  static const String keyIsLoggedIn   = 'is_logged_in';

  // ── 애니메이션 ────────────────────────────────────
  static const Duration animFast   = Duration(milliseconds: 200);
  static const Duration animMedium = Duration(milliseconds: 350);
  static const Duration animSlow   = Duration(milliseconds: 600);

  // ── 처리 대기 안내 메시지 ────────────────────────
  static const String processingMsg =
      '처리중입니다. 잠시만 기다려주세요.\n하루 2분이 걸릴 수 있습니다.';

  // ── 녹음 모드 ────────────────────────────────────
  static const List<String> recordModes = [
    '기본 모드',
    '퀵 개인화',
    '개인화 음성 1',
    '개인화 음성 2',
    '개인화 음성 3',
  ];

  // ── 더미 응답 (데모용) ────────────────────────────
  static const List<String> demoResponses = [
    '오늘 하루도 정말 수고했어요! 녹음하신 내용을 잘 들었어요. 무엇이든 도움이 필요하면 언제든지 말해줘요 ♡',
    '방금 하신 말씀이 정말 중요하게 느껴져요. 제가 기억해둘게요. 더 얘기해줄 수 있어요?',
    '네, 이해했어요! 그 부분은 제가 도와드릴 수 있을 것 같아요. 조금 더 자세히 설명해주시면 어떨까요?',
    '정말요? 그런 일이 있었군요. 힘드셨겠다... 저는 항상 곁에 있을게요 ♡',
    '좋아요! 그 아이디어 정말 멋진 것 같아요. 어떻게 진행할 계획인지 들을 수 있을까요?',
  ];
}