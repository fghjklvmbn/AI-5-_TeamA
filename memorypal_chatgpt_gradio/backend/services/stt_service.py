import requests


STT_URL = (
    "http://localhost:8001"
)


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

                f"{STT_URL}/transcribe",

                files={
                    "audio": f
                }
            )

        response.raise_for_status()

        return response.json()