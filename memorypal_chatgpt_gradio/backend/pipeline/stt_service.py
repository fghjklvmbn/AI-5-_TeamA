from backend.pipeline.clients.stt_client import (
    STTClient
)
from backend.configs.service_config import STT_HOST

import requests
import tempfile

class STTService:

    def __init__(self):

        self.client = STTClient(
            host={STT_HOST}
        )

    @staticmethod
    def transcribe(
        audio_source
    ):

        if audio_source.startswith(
            "http"
        ):

            response = (
                requests.get(
                    audio_source,
                    timeout=30
                )
            )

            response.raise_for_status()

            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False
            ) as tmp:

                tmp.write(
                    response.content
                )

                audio_path = (
                    tmp.name
                )

        else:

            audio_path = (
                audio_source
            )

        with open(
            audio_path,
            "rb"
        ) as f:

            response = requests.post(

                f"{STT_HOST}/transcribe",

                files={
                    "audio": f
                }
            )

        response.raise_for_status()

        return response.json()