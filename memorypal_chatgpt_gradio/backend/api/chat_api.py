from backend.pipeline.manager import (
    PipelineManager
)

from backend.pipeline.clients.llm_client import (
    LLMClient
)

from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

from backend.configs.service_config import (
    LLM_BASE_URL,
    ARCHIVE_HOST,
    ARCHIVE_PORT
)


archive_client = ArchiveClient(
    ARCHIVE_HOST,
    ARCHIVE_PORT
)

llm_client = LLMClient(
    base_url=LLM_BASE_URL
)

pipeline = PipelineManager(
    stt_client=None,
    llm_client=llm_client,
    archive_client=archive_client
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