# backend/pipeline/manager.py
from backend.pipeline.clients.stt_client import STTClient
from backend.pipeline.clients.llm_client import LLMClient
from backend.pipeline.clients.tts_client import TTSClient


class PipelineManager:

    def __init__(
        self,
        stt_client,
        llm_client,
        tts_client
    ):

        self.stt = stt_client
        self.llm = llm_client
        self.tts = tts_client

    def run(
        self,
        audio_path,
        voice
    ):

        stt_result = self.stt.transcribe(
            audio_path
        )

        llm_result = self.llm.generate(
            stt_result["text"]
        )

        tts_result = self.tts.synthesize(
            llm_result["answer"],
            voice
        )

        return {
            "text":
            llm_result["answer"],
            "audio":
            tts_result["audio_path"]
        }