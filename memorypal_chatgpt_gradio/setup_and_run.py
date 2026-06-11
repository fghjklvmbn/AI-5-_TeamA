import platform
import subprocess
import sys

def run_command(command, shell=True):
    """명령어를 실행하고 에러가 발생하면 프로그램을 중단하는 함수"""
    print(f"\n🚀 실행 중: {command}")
    try:
        # 윈도우와 리눅스의 shell 특성 대응
        subprocess.run(command, shell=shell, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 에러 발생: {e}")
        sys.exit(1)

def main():
    os_type = platform.system()
    print(f"💻 감지된 운영체제: {os_type}")

    # 0. 환경생성
    run_command(f'conda create -n frontend python=3.12 -y')
    run_command(f'conda activate frontend')

    # 1. 필수 패키지 설치 (-e .)
    # 가상환경(venv)을 사용할 경우를 대비해 sys.executable(현재 파이썬 경로)을 사용합니다.
    run_command(f'"{sys.executable}" -m pip install -r requirements.txt')

    # 2. 프론트엔드 서버 실행 (Uvicorn)
    print("\n🌐 프론트엔드 서버를 구동합니다... (Port: 7860)")
    
    # 가상환경 내 python 실행을 안전하게 지원하기 위해 python 파일이름.py 형태로 실행
    try:
        run_command(f'"{sys.executable}" app.py')
    except:
        print("프로그램에 오류가 발생하였습니다. 프로그램을 종료합니다.")
        return 0




if __name__ == "__main__":
    main()