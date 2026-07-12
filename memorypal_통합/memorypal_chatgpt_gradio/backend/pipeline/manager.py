from backend.pipeline.clients.stt_client import STTClient
from backend.pipeline.clients.llm_client import LLMClient
from backend.pipeline.clients.archive_client import ArchiveClient
from backend.pipeline.clients.tts_client import TTSClient
from frontend.config.voice_config import DEFAULT_VOICE


class PipelineManager:

    def __init__(
        self,
        stt_client,
        llm_client,
        archive_client,
        tts_client
    ):

        self.stt = stt_client
        self.llm = llm_client
        self.tts = tts_client
        self.archive = archive_client

    def run(
        self,
        session_id,
        voice_id,
        message=None,
        audio_path=None
    ):
        print("함수 시작")
        # 챗봇용
        if audio_path == None:
            print("채팅 로직 시작")
            llm_result = (
                self.llm.generate(
                    message
                )
            )

            voice_profile = (
                self.archive.get_voice(
                    voice_id
                )
            )

            # 디버깅
            print("voice_profile =", voice_profile)

            tts_result = (
                self.tts.synthesize(

                    text=
                    llm_result["answer"],
                    ref_audio=
                    voice_profile["audio_path"],

                    ref_text=
                    voice_profile["reference_text"]
                )
            )

            output_audio_path = (
                tts_result["audio_path"]
            )

            archive_result = (
                self.archive.save_conversation(
                    {
                        "session_id":
                        session_id,

                        "user_text":
                        message,

                        "assistant_text":
                        llm_result["answer"],

                        "input_audio_path":
                        None,

                        "output_audio_path":
                        output_audio_path,

                        "voice_id":
                        voice_id
                    }
                )
            )
            print("채팅 로직 종료")
            return {
                "conversation_id" : archive_result.get(
                    "id",
                    None
                ),
                "text": llm_result["answer"],
                "audio": output_audio_path
            }
        
        # 음성용 
        if message == None:
            # STT
            print("음성로직 시작")
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

            voice_profile = (
                self.archive.get_voice(
                    voice_id
                )
            )
            print(voice_profile)

            ref_audio = (
                voice_profile["audio_path"]
            )
            
            ref_text = (
                voice_profile["reference_text"]
            )
            
            # TTS
            tts_result = (
                self.tts.synthesize(
                    text=llm_result["answer"],
                    ref_audio=ref_audio,
                    ref_text=ref_text
                )
            )

            output_audio_path = (
                tts_result["audio_path"]
            )


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
                        voice_id
                    }
                )
            )

            print("음성로직 종료")
            return {

                "conversation_id":
                archive_result.get(
                    "id",
                    None
                ),

                "user_text" : stt_result["text"],

                "text":
                llm_result["answer"],

                "audio":
                output_audio_path
            }