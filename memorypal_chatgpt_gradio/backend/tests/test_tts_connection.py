import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.clients.tts_client import (
    TTSClient
)

from backend.configs.service_config import (
    TTS_HOST,
    TTS_PORT
)


tts_client = TTSClient(
    TTS_HOST,
    TTS_PORT
)


result = (
    tts_client.synthesize(
        text="안녕하세요 MemoryPal 입니다.",
        ref_audio="https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav",
        ref_text="Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it! And thanks to you."
    )
)

print(result)