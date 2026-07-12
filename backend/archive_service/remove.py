import os
import shutil
import platform
from pathlib import Path

def remove_directory(dir_path):
    """폴더를 안전하게 강제 삭제하는 함수"""
    path = Path(dir_path)
    if path.exists() and path.is_dir():
        try:
            # 윈도우에서 읽기 전용 파일 권한 문제 해결을 위한 오류 처리 핸들러
            def onerror(func, path, exc_info):
                import stat
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR)
                    func(path)
                else:
                    raise
            
            shutil.rmtree(path, onerror=onerror)
            print(f"🗑️ 삭제 완료: {path}")
        except Exception as e:
            print(f"❌ {path} 삭제 중 오류 발생: {e}")
    else:
        print(f"🔍 찾을 수 없음 (이미 삭제됨): {path}")

def clean_pycache(base_dir="."):
    """현재 디렉토리 하위의 모든 __pycache__ 폴더를 찾아 삭제"""
    print("🔍 하위 폴더에서 __pycache__ 탐색 중...")
    count = 0
    # rglob을 이용해 모든 하위 디렉토리 내 __pycache__ 검색
    for p in list(Path(base_dir).rglob("__pycache__")):
        if p.is_dir():
            try:
                shutil.rmtree(p)
                print(f"🗑️ 캐시 삭제: {p}")
                count += 1
            except Exception as e:
                print(f"❌ {p} 캐시 삭제 실패: {e}")
    
    if count == 0:
        print("✨ 삭제할 __pycache__가 없습니다.")
    else:
        print(f"✨ 총 {count}개의 __pycache__ 폴더를 제거했습니다.")

def main():
    os_type = platform.system()
    print(f"💻 감지된 운영체제: {os_type}")
    print("🧹 파이썬 캐시 정리를 시작합니다.\n" + "="*40)

    # 2. 모든 __pycache__ 폴더 제거
    print(f"\n1. [__pycache__] 생성된 컴파일 캐시 제거 중...")
    clean_pycache()

    print("="*40 + "\n🎉 모든 정리가 완료되었습니다!")

if __name__ == "__main__":
    main()