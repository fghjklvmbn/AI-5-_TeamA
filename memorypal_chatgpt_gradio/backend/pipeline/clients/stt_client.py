import requests


class STTClient:

    def __init__(
        self,
        host: str,
        port: int
    ):
        self.base_url = (
            f"http://{host}:{port}"
        )

    def health(self):

        response = requests.get(
            f"{self.base_url}/health",
            timeout=10
        )

        return response.json()

    def transcribe(
        self,
        audio_path: str
    ):

        with open(
            audio_path,
            "rb"
        ) as audio_file:

            response = requests.post(
                f"{self.base_url}/transcribe",
                files={
                    "audio": audio_file
                },
                timeout=300
            )

        response.raise_for_status()

        return response.json()