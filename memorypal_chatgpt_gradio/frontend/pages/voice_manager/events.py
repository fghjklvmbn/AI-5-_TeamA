from backend.services.stt_service import (
    STTService
)

from frontend.services.archive_service import (
    ArchiveService
)

import gradio as gr

def register_voice(

    voice_name,
    audio_path

):

    if not voice_name:

        return (
            "음성 이름을 입력하세요."
        )

    if not audio_path:

        return (
            "음성 파일을 선택하세요."
        )

    stt_result = (
        STTService.transcribe(
            audio_path
        )
    )

    payload = {

        "voice_name":
        voice_name,

        "audio_path":
        audio_path,

        "reference_text":
        stt_result["text"],

        "description":
        ""
    }

    ArchiveService.create_voice(
        payload
    )

    result = (
        ArchiveService.create_voice(
            payload
        )
    )

    print(result)
    return (
        "등록 완료"
    )


def load_voice_list():

    voices = (
        ArchiveService
        .get_voice_list()
    )

    return gr.update(

        choices=[

            (
                item["voice_name"],
                item["id"]
            )

            for item in voices
        ]
    )

def select_voice(
    voice_id
):

    return voice_id