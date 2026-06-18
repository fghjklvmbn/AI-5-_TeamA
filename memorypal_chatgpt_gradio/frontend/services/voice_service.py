from frontend.services.archive_service import (
    ArchiveService
)


class VoiceService:

    @staticmethod
    def get_voice_choices():

        voices = (
            ArchiveService.get_voice_list()
        )

        return [
            (
                voice["voice_name"],
                voice["id"]
            )
            for voice in voices
            ]