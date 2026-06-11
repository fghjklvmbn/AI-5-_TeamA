import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.manager import (
    PipelineManager
)

from backend.pipeline.clients.llm_client import (
    LLMClient
)

from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

from backend.pipeline.clients.tts_client import (
    TTSClient
)

from backend.configs.service_config import (
    LLM_BASE_URL,
    ARCHIVE_HOST,
    ARCHIVE_PORT,
    TTS_HOST,
    TTS_PORT
)


archive_client = ArchiveClient(
    ARCHIVE_HOST,
    ARCHIVE_PORT
)

llm_client = LLMClient(
    base_url=LLM_BASE_URL
)

tts_client = TTSClient(
    TTS_HOST,
    TTS_PORT
)

pipeline = PipelineManager(
    stt_client=None,
    llm_client=llm_client,
    archive_client=archive_client,
    tts_client=tts_client
)

session = (
    archive_client.create_session(
        "TTS 통합 테스트"
    )
)

result = (
    pipeline.run_text_with_tts(
        session["id"],
        "안녕하세요"
    )
)

print(result)