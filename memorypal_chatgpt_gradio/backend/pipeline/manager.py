# backend/pipeline/manager.py

class PipelineManager:

    def __init__(
        self,
        stt,
        llm,
        tts
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts

    def run(
        self,
        audio_path,
        voice_profile
    ):

        text = self.stt.transcribe(
            audio_path
        )

        llm_result = self.llm.generate(
            text
        )

        audio_result = self.tts.generate(
            llm_result,
            voice_profile
        )

        return {
            "text": llm_result,
            "audio": audio_result
        }