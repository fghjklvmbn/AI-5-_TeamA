import torch

MODEL_NAME = (
    "Qwen/Qwen3-TTS-0.6B"
)

class QwenTTSModel:

    _model = None
    _processor = None

    @classmethod
    def load(cls):

        if cls._model is not None:
            return

        print(
            "Qwen3-TTS 모델 로딩중..."
        )

        from transformers import (
            AutoProcessor,
            AutoModel
        )

        cls._processor = (
            AutoProcessor.from_pretrained(
                MODEL_NAME
            )
        )

        cls._model = (
            AutoModel.from_pretrained(
                MODEL_NAME,
                torch_dtype="auto",
                device_map="auto"
            )
        )

        print(
            "Qwen3-TTS 모델 로딩 완료"
        )