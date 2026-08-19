# LLM 서버 VRAM 모니터 설정

실제 LM Studio 컴퓨터(`192.168.2.41`)에서 실행합니다. 브라우저에는 토큰이나 GPU API를 직접 노출하지 않고, MemoryPal Gateway(`192.168.2.75`)만 LAN으로 접근합니다. 저장소 루트의 `dist/MemoryPal-LLM-Monitor.zip`을 LLM 서버로 복사하면 됩니다.

1. 이 저장소를 LLM 서버 컴퓨터에도 복사하거나 최신 변경을 가져옵니다.
2. Gateway에서 사용하는 `MEMORYPAL_MODEL_SERVICE_TOKEN`과 동일한 값을 UTF-8 텍스트 파일에 저장합니다. 예: `C:\MemoryPalSecrets\model-service-token.txt`
3. 관리자 PowerShell에서 방화벽 규칙을 추가합니다.

```powershell
New-NetFirewallRule -DisplayName "MemoryPal LLM Resource Monitor" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8101 -RemoteAddress 192.168.2.75
```

4. 일반 PowerShell에서 모니터를 시작합니다.

```powershell
Set-Location C:\path\to\AI-5-_TeamA
.\deploy\lmstudio\run-resource-monitor.ps1 -TokenFile C:\MemoryPalSecrets\model-service-token.txt
```

5. LLM 서버에서 상태를 확인합니다.

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8011/health
```

Gateway 컴퓨터의 `.env`에는 다음 값을 사용합니다.

```dotenv
MEMORYPAL_MONITOR_LLM_URL=http://192.168.2.41:8101
```

Gateway를 재시작하면 설정의 모델 관리 카드에 `LLM 서버 사용 가능 VRAM`이 표시됩니다. 자원 엔드포인트가 꺼져 있거나 인증에 실패하면 로컬 PC의 GPU 수치로 대체하지 않고 VRAM 항목을 숨깁니다.
