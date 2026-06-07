import shutil
from pathlib import Path
from datetime import datetime


class RecordingService:

    RECORD_DIR = Path(
        "storage/recordings"
    )

    @classmethod
    def save_audio(
        cls,
        audio_path : str
    ) -> str:

        cls.RECORD_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        filename = datetime.now().strftime(
            "REC_%Y%m%d_%H%M%S.wav"
        )

        target_path = (cls.RECORD_DIR / filename)

        shutil.copy(
            audio_path,
            target_path
        )

        return str(target_path)