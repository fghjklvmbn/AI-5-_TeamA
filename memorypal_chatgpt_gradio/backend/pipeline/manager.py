# backend/pipeline/manager.py
from backend.pipeline.clients.stt_client import STTClient
from backend.pipeline.clients.llm_client import LLMClient
from backend.pipeline.clients.tts_client import TTSClient


class PipelineManager:

    def __init__(
        self,
        stt_client,
        llm_client,
        tts_client=None
    ):

        self.stt = stt_client
        self.llm = llm_client
        self.tts = tts_client

    def run(
        self,
        audio_path
    ):

        stt_result = (
            self.stt.transcribe(
                audio_path
            )
        )

        llm_result = (
            self.llm.generate(
                stt_result["text"]
            )
        )

        return {
            "user_text":
            stt_result["text"],

            "answer":
            llm_result["answer"]
        }