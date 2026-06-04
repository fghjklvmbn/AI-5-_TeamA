# 🎙️ 개인 음성 AI 메모리 앱 — Flutter 프론트엔드

## 프로젝트 구조

```
voice_memory_app/
├── lib/
│   ├── main.dart                          # 앱 진입점, DI 설정, 라우팅
│   ├── core/
│   │   ├── constants/
│   │   │   └── app_constants.dart         # API 엔드포인트, UI 상수
│   │   ├── theme/
│   │   │   └── app_theme.dart             # 디자인 시스템 (색상, 타이포, 컴포넌트)
│   │   └── network/
│   │       ├── stt_service.dart           # STT 서비스 (Native / Custom 듀얼 모드)
│   │       ├── llm_service.dart           # LLM 서비스 (스트리밍 + E2E 파이프라인)
│   │       └── tts_service.dart           # TTS 서비스 (합성 + 재생)
│   ├── features/
│   │   ├── record/                        # 음성 녹음 Feature
│   │   │   ├── domain/entities/
│   │   │   └── presentation/
│   │   │       ├── bloc/record_bloc.dart  # 녹음 상태 관리 (BLoC)
│   │   │       ├── pages/record_page.dart # 녹음 화면
│   │   │       └── widgets/
│   │   │           ├── waveform_visualizer.dart  # 실시간 파형
│   │   │           └── processing_indicator.dart # STT/LLM 처리 표시
│   │   ├── memory/                        # 메모리 목록 Feature
│   │   │   ├── domain/entities/
│   │   │   │   └── memory.dart           # Memory 도메인 엔티티
│   │   │   └── presentation/
│   │   │       └── pages/memory_list_page.dart
│   │   └── chat/                          # AI 대화 Feature
│   │       ├── domain/entities/
│   │       │   └── chat_message.dart     # ChatMessage 엔티티
│   │       └── presentation/
│   │           └── pages/chat_page.dart
│   └── shared/
│       └── widgets/
│           └── main_shell.dart           # 바텀 네비게이션 쉘
└── pubspec.yaml
```

## 아키텍처

### Clean Architecture (Feature-first)
- **Domain**: Entity + Repository Interface + UseCase
- **Data**: 외부 API/DB 구현체
- **Presentation**: BLoC + Page + Widget

### STT 파이프라인 전략

```
[Phase 1] NativeSttService  ← 현재 사용
  └─ 기기/서버 자체 STT 활용
  └─ 정확도 보통, 빠른 개발

[Phase 2] CustomSttService  ← 정확도 개선 후 교체
  └─ 자체 개발 Transformer STT 모델
  └─ 단어 타임스탬프, 높은 정확도
```

교체 방법: `main.dart`의 `_setupDependencies()`에서
```dart
// Phase 1
getIt.registerLazySingleton<SttService>(() => NativeSttService());
// Phase 2로 교체
getIt.registerLazySingleton<SttService>(() => CustomSttService());
```

### E2E 파이프라인 (WebSocket)

```
[Flutter] → (음성 청크) → [WS /ws/pipeline] → STT → LLM → TTS → [Flutter]
           ←─── stt_partial ────────────────────────────────────────
           ←─── stt_final ─────────────────────────────────────────
           ←─── llm_delta (스트리밍) ───────────────────────────────
           ←─── tts_chunk (오디오) ────────────────────────────────
```

### 백엔드 API 명세 (Flutter 기준)

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/stt/transcribe` | POST (multipart) | 파일 STT |
| `/stt/stream` | WS | 실시간 STT |
| `/llm/chat` | POST | 단일 응답 |
| `/llm/stream` | POST (SSE) | 스트리밍 응답 |
| `/llm/summarize` | POST | 메모리 요약 |
| `/llm/tags` | POST | 태그 생성 |
| `/tts/synthesize` | POST | 텍스트 → 오디오 |
| `/tts/stream` | POST (stream) | 스트리밍 TTS |
| `/memories` | GET/POST | 메모리 CRUD |
| `/memories/search` | POST | 시맨틱 검색 |
| `/ws/pipeline` | WS | E2E 파이프라인 |

## 실행 방법

```bash
cd voice_memory_app
flutter pub get
flutter run
```

## 다음 개발 항목 (우선순위순)

1. [ ] MemoryBloc 구현 + Hive 로컬 저장
2. [ ] ChatBloc 구현 + LLM 스트리밍 연결
3. [ ] Memory 상세 화면
4. [ ] 설정 화면 (STT 모드 전환, 백엔드 URL 설정)
5. [ ] 온보딩 화면
6. [ ] TTS 재생 컨트롤러 완성
7. [ ] WebSocket E2E 파이프라인 연결
8. [ ] 검색 + 시맨틱 검색 UI
9. [ ] 메모리 연관 그래프 시각화

## 디자인 시스템

- **색상**: Deep Night Blue 기반, Electric Cyan 액센트
- **폰트**: Pretendard (한국어 최적화)
- **애니메이션**: flutter_animate 라이브러리
- **테마**: 다크 모드 전용
