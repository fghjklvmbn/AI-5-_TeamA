# MemoryPal LLM 서버 모니터

LM Studio가 실행되는 서버에서 CPU, RAM, NVIDIA CUDA 사용률과 VRAM 총량·사용량·여유량을 15초마다 수집합니다. 인증된 MemoryPal Gateway만 수치를 읽을 수 있습니다.

## Windows

1. Gateway의 `MEMORYPAL_MODEL_SERVICE_TOKEN`과 동일한 32자 이상 값을 별도 텍스트 파일에 저장합니다.
2. 압축을 푼 폴더에서 다음을 실행합니다.

```powershell
.\start-monitor.ps1 -TokenFile C:\MemoryPalSecrets\model-service-token.txt
```

배치 파일을 쓰려면 `start-monitor.bat -TokenFile C:\MemoryPalSecrets\model-service-token.txt`를 실행합니다. 최초 실행은 가상환경과 Python 패키지를 설치합니다.

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

Gateway에는 `MEMORYPAL_MONITOR_LLM_URL=http://192.168.2.41:8101`을 설정합니다. `/health`는 상태 확인용이며, `/v1/metrics/current`와 `/v1/metrics/history`는 공유 Bearer 토큰이 필요합니다.
