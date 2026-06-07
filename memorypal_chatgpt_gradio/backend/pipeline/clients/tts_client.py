import requests


class TTSClient:

    def __init__(
        self,
        server_url
    ):
        self.server_url = server_url

    def synthesize(
        self,
        text,
        voice
    ):

        response = requests.post(
            f"{self.server_url}/synthesize",
            json={
                "text": text,
                "voice": voice
            }
        )

        return response.json()