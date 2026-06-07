import requests


class STTClient:

    def __init__(
        self,
        server_url
    ):
        self.server_url = server_url

    def transcribe(
        self,
        audio_path
    ):

        with open(
            audio_path,
            "rb"
        ) as audio:

            response = requests.post(
                f"{self.server_url}/transcribe",
                files={
                    "audio": audio
                }
            )

        return response.json()