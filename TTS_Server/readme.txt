qwen3-tts는 특수한 환경을 요구하므로 되도록이면 아나콘다 등 가상화 공간을 필수적으로 사용하여야 한다.

구성 및 설치방법
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts

pip install -U qwen-tts


로드시 필수 항목
git clone https://github.com/QwenLM/Qwen3-TTS.git
cd Qwen3-TTS
pip install -e .



엔비디아 제품군일경우
pip install -U flash-attn --no-build-isolation


TTS port : 8003

서버 실행 명령어
uvicorn app:app --reload --host 0.0.0.0 --port 8003