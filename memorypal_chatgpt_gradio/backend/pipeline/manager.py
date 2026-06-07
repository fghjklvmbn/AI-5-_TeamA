# backend/pipeline/manager.py
from backend.pipeline.clients.stt_client import STTClient
from backend.pipeline.clients.llm_client import LLMClient
from backend.pipeline.clients.archive_client import ArchiveClient


class PipelineManager:

    def __init__(
        self,
        stt_client,
        llm_client,
        archive_client,
        tts_client=None
    ):

        self.stt = stt_client
        self.llm = llm_client
        self.tts = tts_client
        self.archive = archive_client

    def run(
        self,
        session_id,
        audio_path,
        voice=None
    ):

        # STT
        stt_result = (
            self.stt.transcribe(
                audio_path
            )
        )

        # LLM
        llm_result = (
            self.llm.generate(
                stt_result["text"]
            )
        )

        # TTS 미구현 상태
        output_audio_path = None

        # Archive 저장
        archive_result = (
            self.archive.save_conversation(
                {
                    "session_id":
                    session_id,

                    "user_text":
                    stt_result["text"],

                    "assistant_text":
                    llm_result["answer"],

                    "input_audio_path":
                    audio_path,

                    "output_audio_path":
                    output_audio_path,

                    "voice_id":
                    None
                }
            )
        )

        return {

            "conversation_id":
            archive_result["id"],

            "text":
            llm_result["answer"],

            "audio":
            output_audio_path
        }
    
    def run_text(
        self,
        session_id,
        user_text
    ):

        llm_result = (
            self.llm.generate(
                user_text
            )
        )

        archive_result = (
            self.archive.save_conversation(
                {
                    "session_id":
                    session_id,

                    "user_text":
                    user_text,

                    "assistant_text":
                    llm_result["answer"],

                    "input_audio_path":
                    None,

                    "output_audio_path":
                    None,

                    "voice_id":
                    None
                }
            )
        )

        return {

            "conversation_id":
            archive_result["id"],

            "text":
            llm_result["answer"]
        }
        # return {

        #     "conversation_id":
        #     archive_result.get(
        #         "id",
        #         None
        #     ),

        #     "text":
        #     llm_result["answer"]
        # }
        