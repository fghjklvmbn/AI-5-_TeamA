from pathlib import Path
from datetime import datetime


class SynthesisService:

    OUTPUT_DIR = Path(
        "outputs"
    )

    @classmethod
    def synthesize(
        cls,
        text
    ):

        cls.OUTPUT_DIR.mkdir(
            exist_ok=True
        )

        output_path = (
            cls.OUTPUT_DIR /
            f"tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        )

        return str(output_path)