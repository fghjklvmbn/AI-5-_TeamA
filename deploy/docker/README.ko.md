# MemoryPal Docker 실행 (Windows / Linux)

## 공통 요구 사항

- Docker Engine 또는 Docker Desktop
- Docker Compose v2
- 모델 서비스를 실행할 경우 충분한 디스크와 메모리
  - Whisper Turbo 모델: 약 1.5GB 다운로드
  - Qwen3-TTS 모델 및 런타임: 수 GB 다운로드

비밀값은 첫 실행 때 `.runtime/docker.env`에 자동 생성됩니다. 이 파일은 Git에서
제외되며 외부에 공유하면 안 됩니다.

## Windows

핵심 서비스만 시작:

```powershell
.\docker-up.cmd
```

STT/TTS도 함께 시작하고 장치를 자동 감지:

```powershell
.\docker-up.cmd -WithModels
```

CPU 강제 또는 NVIDIA 강제:

```powershell
.\docker-up.cmd -WithModels -CpuOnly
.\docker-up.cmd -WithModels -Nvidia
```

Windows Docker Desktop는 AMD ROCm 장치의 Linux 컨테이너 직접 전달을 지원하지
않습니다. 지원되는 Radeon/Ryzen 장치라면 AMD의 Windows용 ROCm PyTorch를 호스트에
설치해 STT/TTS를 네이티브로 실행할 수 있습니다. 핵심 Docker 스택은 기본적으로
`host.docker.internal:8001`과 `host.docker.internal:8003`을 사용합니다. Docker 안에서
모델을 실행하면 AMD GPU 대신 CPU로 안전하게 폴백합니다.

## Linux

핵심 서비스만 시작:

```bash
bash ./docker-up.sh
```

STT/TTS도 함께 시작하고 NVIDIA CUDA, AMD ROCm, CPU 순으로 자동 선택:

```bash
bash ./docker-up.sh --models
```

장치 강제 선택:

```bash
bash ./docker-up.sh --models --cpu-only
bash ./docker-up.sh --models --nvidia
bash ./docker-up.sh --models --amd
```

AMD ROCm 모드는 네이티브 Linux Docker 호스트에서 `/dev/kfd`와 `/dev/dri`가 존재할
때 활성화됩니다. 호스트에 지원되는 AMD GPU와 `amdgpu-dkms` 또는 AMD Container
Toolkit이 설치되어 있어야 합니다. Compose는 AMD 공식 `rocm/pytorch` 이미지를
사용하고 두 장치를 컨테이너에 전달합니다.

PyTorch ROCm은 호환성을 위해 `torch.cuda` API와 `"cuda"` 장치 문자열을 사용하지만,
서비스 health 응답의 `accelerator` 값은 실제 백엔드인 `rocm`으로 표시됩니다.
AMD에서는 NVIDIA CUDA Graph 전용 `faster-qwen3-tts` 대신 upstream Qwen TTS 엔진을
사용합니다.

AMD 공식 참고 자료:

- <https://rocm.docs.amd.com/projects/install-on-linux/en/latest/how-to/docker.html>
- <https://rocm.docs.amd.com/en/latest/compatibility/pytorch-compatibility.html>

## 자동 폴백 규칙

- NVIDIA CUDA 사용 가능: STT는 CUDA, TTS는 faster CUDA 엔진
- AMD ROCm PyTorch 사용 가능: STT는 ROCm, TTS는 upstream ROCm 엔진
- GPU 런타임 없음: STT와 TTS 모두 CPU
- GPU가 강제로 지정됐지만 PyTorch에서 사용할 수 없음: 경고 후 CPU

CPU TTS는 정상 동작하지만 실시간보다 매우 느릴 수 있습니다.

## 접속 주소

- Frontend: <http://127.0.0.1:8081/api_memoripal/main/>
- Admin: <http://127.0.0.1:8082/api_memoripal/manage/>
- Gateway 상태: <http://127.0.0.1:8010/v1/health>
- API 문서: <http://127.0.0.1:8010/docs>
- STT 상태(모델 포함 실행 시): <http://127.0.0.1:8001/health>
- TTS 상태(모델 포함 실행 시): <http://127.0.0.1:8003/health>

로컬 관리자 허용 이메일의 기본값은 `test@test.com`입니다.

LLM은 프로젝트에 포함되지 않으며 기본 주소는 Windows/Linux 모두
`https://developark.duckdns.org/api_memoripal/llm/v1`입니다. 다른 OpenAI 호환 서버를 사용하려면
`.runtime/docker.env`에 `MEMORYPAL_LLM_URL`을 추가하고 다시 실행합니다.

## 중지

Windows:

```powershell
.\docker-down.cmd
```

Linux:

```bash
bash ./docker-down.sh
```

중지 명령은 컨테이너와 네트워크만 제거합니다. PostgreSQL, Redis, 모델 캐시와 음성
업로드 named volume은 유지됩니다.

## 독립 STT/TTS 모델 노드와 Nginx

STT와 TTS는 메인 애플리케이션과 완전히 다른 컴퓨터에서 실행할 수 있습니다. 모델 컴퓨터에서는
Nginx만 `8090` 포트로 공개되고, 내부의 STT `8001` 및 TTS `8003` 포트는 Docker 네트워크에만
노출됩니다. Nginx는 `/stt/`와 `/tts/`를 각 API로 전달합니다.

Linux 모델 컴퓨터:

```bash
# 두 모델을 모두 실행하며 GPU를 자동 감지
bash ./docker-model-node-up.sh --public-url http://192.168.0.20:8090

# 서로 다른 컴퓨터에 나눠 실행하는 예
bash ./docker-model-node-up.sh --stt-only --amd --public-url http://192.168.0.20:8090
bash ./docker-model-node-up.sh --tts-only --nvidia --public-url http://192.168.0.21:8090
```

Windows 모델 컴퓨터(Docker Desktop):

```powershell
.\docker-model-node-up.ps1 -PublicUrl http://192.168.0.20:8090
.\docker-model-node-up.ps1 -SttOnly -Nvidia -PublicUrl http://192.168.0.20:8090
.\docker-model-node-up.ps1 -TtsOnly -CpuOnly -PublicUrl http://192.168.0.21:8090
```

첫 실행 시 `.runtime/model-node.env`가 생성됩니다. 그 파일의
`MEMORYPAL_MODEL_SERVICE_TOKEN` 값을 메인 컴퓨터의 `.runtime/docker.env`에 있는 같은 항목으로
복사해야 합니다. STT와 TTS를 두 컴퓨터에 나누면 두 노드 모두 동일한 토큰을 사용합니다.

메인 컴퓨터의 `.runtime/docker.env`에는 다음처럼 원격 주소를 설정합니다.

```dotenv
MEMORYPAL_STT_URL=http://192.168.0.20:8090/stt
MEMORYPAL_TTS_URL=http://192.168.0.21:8090/tts
MEMORYPAL_TTS_PUBLIC_URL=http://192.168.0.21:8090/tts
```

그 후 메인 컴퓨터에서는 모델을 포함하지 않고 평소처럼 `docker-up.cmd` 또는
`bash ./docker-up.sh`를 실행합니다. 참조 음성은 공유 디스크 경로 대신 인증된 Archive API에서
읽어 원격 TTS API에 업로드되므로 양쪽 컴퓨터가 같은 파일시스템을 사용할 필요가 없습니다.

상태 확인 주소:

- Nginx: `http://MODEL_IP:8090/health`
- STT: `http://MODEL_IP:8090/stt/health`
- TTS: `http://MODEL_IP:8090/tts/health`

모델 노드 중지:

```powershell
.\docker-model-node-down.ps1
```

```bash
bash ./docker-model-node-down.sh
```

인터넷에 직접 공개할 경우 현재 HTTP Nginx 앞에 TLS 리버스 프록시 또는 VPN을 두십시오. 사설망에서도
방화벽은 메인 서버에서 오는 `8090/tcp`만 허용하는 구성이 권장됩니다.
