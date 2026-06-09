import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.manager import (
    PipelineManager
)

from backend.pipeline.clients.stt_client import (
    STTClient
)

from backend.pipeline.clients.llm_client import (
    LLMClient
)

from backend.pipeline.clients.tts_client import (
    TTSClient
)

from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

from backend.configs.service_config import *


stt_client = STTClient(
    STT_HOST,
    STT_PORT
)

llm_client = LLMClient(
    base_url=LLM_BASE_URL
)

tts_client = TTSClient(
    TTS_HOST,
    TTS_PORT
)

archive_client = ArchiveClient(
    ARCHIVE_HOST,
    ARCHIVE_PORT
)

pipeline = PipelineManager(
    stt_client=stt_client,
    llm_client=llm_client,
    tts_client=tts_client,
    archive_client=archive_client
)

session = (
    archive_client.create_session(
        "음성 파이프라인 테스트"
    )
)

result = (
    pipeline.run(
        session_id=session["id"],
        audio_path="test.wav"
    )
)

print(result)