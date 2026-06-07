import requests


class LLMClient:

    def __init__(
        self,
        server_url
    ):
        self.server_url = server_url

    def generate(
        self,
        text
    ):

        response = requests.post(
            f"{self.server_url}/generate",
            json={
                "text": text
            }
        )

        return response.json()