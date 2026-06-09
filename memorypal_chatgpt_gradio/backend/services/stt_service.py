import requests

from backend.configs.service_config import STT_HOST

class STTService:

    @staticmethod
    def transcribe(
        audio_path
    ):

        with open(
            audio_path,
            "rb"
        ) as f:

            response = requests.post(

                f"http://{STT_HOST}/transcribe",

                files={
                    "audio": f
                }
            )

        response.raise_for_status()

        return response.json()