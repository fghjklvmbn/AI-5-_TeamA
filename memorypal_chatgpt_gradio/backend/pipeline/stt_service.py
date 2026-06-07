from backend.pipeline.clients.stt_client import (
    STTClient
)

from backend.configs.yaml_loaders import (
    load_yaml
)


class STTService:

    def __init__(self):

        config = load_yaml(
            "backend/configs/stt.yaml"
        )

        self.client = STTClient(
            host=config["server"]["host"],
            port=config["server"]["port"]
        )

    def transcribe(
        self,
        audio_path
    ):

        return self.client.transcribe(
            audio_path
        )