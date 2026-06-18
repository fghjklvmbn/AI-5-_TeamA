import requests


class TTSClient:

    def __init__(
        self,
        host
    ):

        self.base_url = (
            f"{host}"
        )

    def synthesize(
        self,
        text,
        ref_audio,
        ref_text,
        language="korean"
    ):

        response = requests.post(

            f"{self.base_url}/synthesize",

            json={
                "text": text,
                "ref_audio": ref_audio,
                "ref_text": ref_text,
                "language": language
            }
        )

        response.raise_for_status()

        return response.json()