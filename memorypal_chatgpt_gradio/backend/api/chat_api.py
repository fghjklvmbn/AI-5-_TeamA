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

from backend.pipeline.clients.stt_client import (
    STTClient
)

from backend.configs.service_config import (
    LLM_BASE_URL,
    ARCHIVE_HOST,
    ARCHIVE_PORT,
    TTS_HOST,
    TTS_PORT,
    STT_HOST,
    STT_PORT
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

stt_client = STTClient(
    STT_HOST,
    STT_PORT
)

pipeline = PipelineManager(
    stt_client=stt_client,
    llm_client=llm_client,
    archive_client=archive_client,
    tts_client=tts_client
)


def send_message(
    session_id,
    message
):

    return (
        pipeline.run_text(
            session_id,
            message
        )
    )