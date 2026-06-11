import platform
import subprocess
import sys

# 콘다 환경 체크
def check_conda_env(env_name):
    try:
        # 'conda env list' 명령어를 실행하여 출력 결과를 가져옵니다.
        result = subprocess.run('conda env list', shell=True, capture_output=True, text=True, check=True)
        
        # 출력 결과물(텍스트)에서 내가 찾는 환경 이름이 있는지 검사합니다.
        # 공백이나 경로 구분을 위해 이름 앞뒤를 고려하여 검사하는 것이 안전합니다.
        lines = result.stdout.splitlines()
        for line in lines:
            if line.strip() and not line.startswith('#'):
                # 각 행의 첫 번째 단어가 환경 이름입니다.
                existing_env = line.split()[0]
                if existing_env == env_name:
                    return True
        return False
    except FileNotFoundError:
        print("에러: 시스템에 conda가 설치되어 있지 않거나 PATH가 설정되지 않았습니다.")
        return False
    except subprocess.CalledProcessError:
        print("에러: conda env list 명령어를 실행하지 못했습니다.")
        return False
        
# 아나콘다 설치 체크
def check_anaconda():
    try:
        # 'conda env list' 명령어를 실행하여 출력 결과를 가져옵니다.
        result = subprocess.run('conda --version', shell=True, capture_output=True, text=True, check=True)
        
        # 출력 결과물(텍스트)에서 내가 찾는 환경 이름이 있는지 검사합니다.
        # 공백이나 경로 구분을 위해 이름 앞뒤를 고려하여 검사하는 것이 안전합니다.
        if "conda" in result.stdout:
            return True
        return False
    
    except FileNotFoundError:
        print("에러: 시스템에 conda가 설치되어 있지 않거나 PATH가 설정되지 않았습니다.")
        print("만약 시스템에 anaconda가 설치하지 않았다면 https://www.anaconda.com/download/success?reg=skipped 링크로 이동하여 설치해주시기 바랍니다.")
        return False
    except subprocess.CalledProcessError:
        print("에러: conda env list 명령어를 실행하지 못했습니다.")
        return False

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

    # 0. 환경생성 및 체크
    if check_anaconda():
        print("아나콘다가 설치되어 있습니다.")
    else:
        return 0
    
    target_env = "gradio"

    if check_conda_env(target_env):
        print(f"[{target_env}] 환경이 이미 존재하므로 이후 코드를 건너뜁니다.")
    else:
        print(f"[{target_env}] 환경이 없습니다. 새로 생성을 시작합니다...")
        run_command(command=f"conda create -n {target_env} python=3.12 -y")
        
    # 가상환경 실행
    run_command(command=f"conda activate {target_env}")

    # 1. 필수 패키지 설치
    # 가상환경(venv)을 사용할 경우를 대비해 sys.executable(현재 파이썬 경로)을 사용합니다.

    # nvidia 체크
    run_command(f'"{sys.executable}" -m pip install -r requirements.txt')

    # 3. STT 서버 실행 (Uvicorn)
    print("\n🌐 Uvicorn STT 서버를 구동합니다... (Port: 8001)")

    # 가상환경 내 uvicorn 실행을 안전하게 지원하기 위해 python -m uvicorn 형태로 실행
    try:
        run_command(f'"{sys.executable}" -m uvicorn app:app --reload --host 0.0.0.0 --port 8001')
    except:
        print("프로그램이 종료되었습니다.")
        return 0

if __name__ == "__main__":
    main()