# 서비스 하드웨어 모니터

각 모니터는 서비스 프로세스와 자식 프로세스의 CPU/RAM, 호스트 RAM, 응답 시간을 15초마다 수집합니다. LLM 모니터만 `nvidia-smi`를 호출해 GPU/CUDA 및 VRAM 총량·사용량·여유량을 추가합니다.

| 서비스 | 모니터 포트 |
|---|---:|
| STT | 8100 |
| LLM | 8101 |
| TTS | 8102 |
| Gateway | 8103 |
| Archive | 8104 |

Windows 통합 실행은 루트의 `run.cmd`/`run.ps1`이 로컬 4개 모니터를 함께 시작하며 `stop.cmd`/`stop.ps1`이 먼저 종료합니다. LLM 서버는 `dist/MemoryPal-LLM-Monitor.zip`을 사용합니다.

Linux에서는 서비스 PID를 전달합니다.

```sh
./deploy/monitor/run-service-monitor.sh stt 8100 "$STT_PID" http://127.0.0.1:8001/health /etc/memorypal/model-service-token
```

Gateway는 각 모니터를 15초마다 조회하고 `MEMORYPAL_HARDWARE_MONITOR_LOG_PATH`에 통합 JSONL을 기록합니다. 관리자는 `/v1/admin/services`와 관리자 화면의 `서비스 자원` 메뉴에서 현재 상태와 최근 기록을 확인합니다.
