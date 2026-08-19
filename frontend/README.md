# MemoryPal Frontend

Expo와 React Native로 작성한 Web/iOS/Android 공용 UI입니다. 인증 토큰은 iOS Keychain/Android Keystore에 저장하며, 웹에서는 브라우저 저장소를 사용합니다.

## 개발 실행

프로젝트 루트에서 `install.cmd`를 먼저 실행한 뒤:

```powershell
cd frontend
npm start
```

실기기에서 개발할 때는 루트 `.env`의 `EXPO_PUBLIC_API_URL`을 Gateway가 실행 중인 컴퓨터의 LAN 주소(예: `http://192.168.0.10:8010/v1`)로 설정합니다.

## 정적 내보내기

```powershell
npm run build:web
npm run build:web:project3
```

main은 `dist-main`, project3는 `dist-project3`에 생성됩니다. 두 명령은 서로 다른 base URL과 공개 API URL을 사용하며 각각 `deployment-profile.json`을 기록합니다. 빌드 과정은 `EXPO_PUBLIC_API_URL`과 프로필별 공개 API 변수만 읽고 서버 비밀 환경 변수는 자식 프로세스에서 제거합니다.
