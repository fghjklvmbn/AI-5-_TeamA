from backend.services.recording_service import (
    RecordingService
)


def save_recording(
    audio_path
):

    if audio_path is None:

        return (
            "녹음 파일이 없습니다."
        )

    saved_path = (
        RecordingService.save_audio(
            audio_path
        )
    )

    return (
        f"저장 완료\n{saved_path}"
    )