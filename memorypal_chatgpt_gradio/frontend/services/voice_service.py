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
                "00000000-0000-0000-0000-000000000001"
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