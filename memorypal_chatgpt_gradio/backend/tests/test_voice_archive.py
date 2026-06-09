import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

archive = ArchiveClient(
    "localhost",
    8004
)

voices = (
    archive.get_voice_list()
)

print(voices)