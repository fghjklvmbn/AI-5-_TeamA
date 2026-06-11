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

from backend.configs.service_config import (
    LLM_BASE_URL
)


archive_client = ArchiveClient(
    "localhost",
    8004
)

llm_client = LLMClient(
    base_url=LLM_BASE_URL
)

pipeline = PipelineManager(
    stt_client=None,
    llm_client=llm_client,
    archive_client=archive_client
)

session = (
    archive_client.create_session(
        "파이프라인 테스트"
    )
)

result = (
    pipeline.run_text(
        session["id"],
        "안녕"
    )
)

print(result)