import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

client = ArchiveClient(
    "localhost",
    8004
)

sessions = (
    client.get_session_list()
)

print(
    sessions
)