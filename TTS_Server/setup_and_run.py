import os
import platform
import subprocess
import sys
from pathlib import Path

def run_command(command, shell=True):
    """명령어를 실행하고 에러가 발생하면 프로그램을 중단하는 함수"""
    print(f"\n🚀 실행 중: {command}")
    try:
        # 윈도우와 리눅스의 shell 특성 대응
        subprocess.run(command, shell=shell, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 에러 발생: {e}")
        sys.exit(1)

def check_nvidia():
    """시스템에 NVIDIA GPU 및 CUDA가 있는지 확인"""
    print("🔍 NVIDIA GPU 및 CUDA 환경을 체크하는 중...")
    
    # 1. nvidia-smi 명령어 존재 여부 확인
    try:
        subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("💡 NVIDIA GPU가 감지되지 않았거나 구동 중이 아닙니다. (Flash-attn 설치 건너뜀)")
        return False

    # 2. PyTorch가 설치되어 있다면 CUDA 사용 가능 여부 추가 확인
    try:
        import torch
        if torch.cuda.is_available():
            print("✨ NVIDIA CUDA 환경이 확인되었습니다.")
            return True
    except ImportError:
        # 아직 PyTorch가 설치되지 않은 초기 단계일 수 있으므로 nvidia-smi 결과를 신뢰
        print("💡 PyTorch가 아직 설치되지 않았으나, NVIDIA 하드웨어가 존재합니다.")
        return True

    return False

def main():
    os_type = platform.system()
    print(f"💻 감지된 운영체제: {os_type}")

    # 1. 저장소 클론 및 이동
    repo_dir = "Qwen3-TTS"
    if not os.path.exists(repo_dir):
        run_command("git clone https://github.com/QwenLM/Qwen3-TTS.git")
    else:
        print(f"📂 이미 {repo_dir} 폴더가 존재합니다. 클론을 건너뜁니다.")

    # 파이썬 내부에서 디렉토리 이동 (cd 명령어 역할)
    os.chdir(repo_dir)
    print(f"📂 작업 디렉토리 변경 완료: {os.getcwd()}")

    # 2. 필수 패키지 설치 (-e .)
    # 가상환경(venv)을 사용할 경우를 대비해 sys.executable(현재 파이썬 경로)을 사용합니다.
    run_command(f'"{sys.executable}" -m pip install -e .')

    # 3. 엔비디아 제품군일 경우 flash-attn 설치
    if check_nvidia():
        print("📦 NVIDIA 전용 패키지(flash-attn) 설치를 시작합니다.")
        # 윈도우 환경에서는 flash-attn 빌드가 실패하는 경우가 많아 주의가 필요합니다.
        run_command(f'"{sys.executable}" -m pip install -U flash-attn --no-build-isolation')

    # 4. TTS 서버 실행 (Uvicorn)
    print("\n🌐 Uvicorn TTS 서버를 구동합니다... (Port: 8003)")
    os.chdir('..')

    # 가상환경 내 uvicorn 실행을 안전하게 지원하기 위해 python -m uvicorn 형태로 실행
    run_command(f'"{sys.executable}" -m uvicorn app:app --reload --host 0.0.0.0 --port 8003')

if __name__ == "__main__":
    main()