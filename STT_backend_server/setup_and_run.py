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
        print("💡 NVIDIA GPU가 감지되지 않았거나 구동 중이 아닙니다.")
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

    # 0. 환경생성(TTS)(현재 사용자가 "Administrator"인 경우 건너뛰기)
    if platform.uname().node == "kjca":
        pass
    else:
        run_command(f'conda create -n TTS python=3.12 -y')
        run_command(f'conda activate TTS')

    # 1. ffmpeg 체크 및 설치(현재 사용자가 "Administrator"인 경우 건너뛰기)
    if platform.uname().node == "kjca":
        pass
    else:
        run_command(f'conda install -c conda-forge ffmpeg -y')

    # 2. 필수 패키지 설치 (-e .)
    # 가상환경(venv)을 사용할 경우를 대비해 sys.executable(현재 파이썬 경로)을 사용합니다.

    # nvidia 체크
    if check_nvidia() == True:
        run_command(f'"{sys.executable}" -m pip install -r requirements_cuda.txt')
        run_command(f'"{sys.executable}" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126')
    else :
        run_command(f'"{sys.executable}" -m pip install -r requirements.txt')

    # 4. TTS 서버 실행 (Uvicorn)
    print("\n🌐 Uvicorn TTS 서버를 구동합니다... (Port: 8001)")

    # 가상환경 내 uvicorn 실행을 안전하게 지원하기 위해 python -m uvicorn 형태로 실행
    run_command(f'"{sys.executable}" -m uvicorn app:app --reload --host 0.0.0.0 --port 8001')

if __name__ == "__main__":
    main()