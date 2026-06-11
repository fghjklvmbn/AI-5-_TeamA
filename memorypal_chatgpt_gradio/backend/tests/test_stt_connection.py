import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.stt_service import (
    STTService
)


def main():

    stt = STTService()

    result = stt.transcribe(
        "storage/recordings/REC_20260607_124353.wav"
    )

    print(result)


if __name__ == "__main__":
    # print(ROOT_DIR)
    main()