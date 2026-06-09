from frontend.services.archive_service import (
    ArchiveService
)


class VoiceService:

    @staticmethod
    def get_voice_choices():

        voices = (
            ArchiveService.get_voice_list()
        )

        choices = [
            (
                "기본 음성",
                "default"
            )
        ]

        for voice in voices:

            choices.append(
                (
                    voice["voice_name"],
                    voice["id"]
                )
            )

        return choices