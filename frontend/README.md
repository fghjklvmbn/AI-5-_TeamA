# MemoryPal 모바일 프론트

Expo와 React Native로 작성되어 iOS, Android, Web을 같은 코드로 지원합니다. 참고 프로토타입의 로그인, 메인 음성 버튼, 채팅, 설정 흐름을 유지하면서 실시간 자막과 장기 기억 관리 화면을 추가했습니다.

## 실행

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm start
```

실제 휴대폰에서 테스트할 때는 `.env`의 `EXPO_PUBLIC_API_URL`을 백엔드가 실행 중인 컴퓨터의 LAN 주소(예: `http://192.168.0.10:8000/v1`)로 설정하세요. 웹 브라우저의 마이크는 `localhost`가 아닌 환경에서 HTTPS가 필요합니다. 마이크 권한을 허용하면 약 2.5초 단위로 Whisper Turbo 자막이 갱신되고, 중지 시 누적 자막이 Qwen3.5-4B와 Qwen3-TTS 파이프라인으로 전달됩니다. JWT는 iOS Keychain/Android Keystore에 암호화 저장되며 웹에서는 브라우저 저장소를 사용합니다.
