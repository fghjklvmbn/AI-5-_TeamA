# MemoryPal LLM 서버 자원·로그 수집기

LM Studio가 실행되는 서버에서 CPU, RAM, NVIDIA CUDA 사용률과 VRAM을 15초마다 수집하고, 모델 로드·생성·런타임 로그는 지속적으로 수집합니다. 인증된 MemoryPal Gateway만 수치와 로그를 읽을 수 있습니다.

## Windows

1. LM Studio를 한 번 실행하고 PowerShell에서 `lms --help`가 동작하는지 확인합니다.
2. Gateway의 `MEMORYPAL_MODEL_SERVICE_TOKEN`과 동일한 32자 이상 값을 별도 UTF-8 텍스트 파일에 저장합니다. 토큰 파일에는 토큰 한 줄만 넣습니다.
3. 압축을 푼 폴더에서 다음을 실행합니다.

```powershell
.\start-monitor.ps1 -TokenFile C:\MemoryPalSecrets\model-service-token.txt
```

배치 파일을 쓰려면 `start-monitor.bat -TokenFile C:\MemoryPalSecrets\model-service-token.txt`를 실행합니다. 최초 실행은 가상환경과 Python 패키지를 설치합니다.

`lms`가 PATH에 없다면 직접 지정할 수 있습니다.

```powershell
.\start-monitor.ps1 -TokenFile C:\MemoryPalSecrets\model-service-token.txt -LmsCli "$env:USERPROFILE\.lmstudio\bin\lms.exe"
```

종료할 때는 `.\stop-monitor.bat` 또는 `.\stop-monitor.ps1`을 실행합니다.

Gateway(192.168.2.75)에서만 접근하도록 관리자 PowerShell에서 방화벽을 엽니다.

```powershell
New-NetFirewallRule -DisplayName "MemoryPal LLM Monitor" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8101 -RemoteAddress 192.168.2.75
```

## Linux

```sh
chmod +x start-monitor.sh
./start-monitor.sh /etc/memorypal/model-service-token 8101
```

`nvidia-smi`가 PATH에 있어야 GPU 지표를 수집할 수 있습니다. 서버 부팅 시 함께 실행하려면 Windows 작업 스케줄러 또는 Linux systemd에 위 명령을 등록합니다.

Gateway에는 `MEMORYPAL_MONITOR_LLM_URL=http://192.168.2.41:8101`을 설정합니다. `/health`를 제외한 모든 API는 공유 Bearer 토큰이 필요합니다.

## API 확인

```powershell
$Token = (Get-Content C:\MemoryPalSecrets\model-service-token.txt -Raw).Trim()
$Headers = @{ Authorization = "Bearer $Token" }

Invoke-RestMethod http://127.0.0.1:8101/v1/metrics/current -Headers $Headers
Invoke-RestMethod http://127.0.0.1:8101/v1/logs/status -Headers $Headers
Invoke-RestMethod "http://127.0.0.1:8101/v1/logs/recent?after_cursor=0&limit=100" -Headers $Headers
```

로그 API는 `cursor` 기반입니다. 응답의 `next_cursor`를 다음 요청의 `after_cursor`로 보내면 새 로그만 받을 수 있습니다. `source=server|runtime|model`, `level=info|warn|error`, `model_key=qwen3.5-4b` 필터를 지원합니다.

로그는 `runtime\llm.lmstudio.jsonl`, 자원은 `runtime\llm.hardware.jsonl`에 저장됩니다. LM Studio 모델 입력과 출력 원문, 인증 토큰은 저장 전에 제거됩니다. 파일은 50MB에서 한 세대 순환됩니다.
