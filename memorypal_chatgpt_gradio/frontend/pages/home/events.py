# frontend/pages/home/events.py

import gradio as gr

from backend.models.recoding_state import RecordingState
from backend.services.recording_service import RecordingService

def open_recorder():

    return (
        gr.update(visible=True),      # Audio 컴포넌트 표시
        gr.update(visible=True),      # 저장 버튼 표시
        RecordingState.RECORDING.value
    )

def get_idle_state():
    return RecordingState.IDLE.value

def save_record(audio_path):

    if audio_path is None:

        return (
            RecordingState.ERROR.value,
            "녹음 파일 없음"
        )

    saved_path = RecordingService.save_audio(
        audio_path
    )

    return (
        RecordingState.COMPLETE.value,
        saved_path
    )