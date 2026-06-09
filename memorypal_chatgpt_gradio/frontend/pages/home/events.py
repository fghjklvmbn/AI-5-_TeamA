# frontend/pages/home/events.py

import gradio as gr

from backend.models.recoding_state import RecordingState
from backend.services.recording_service import RecordingService
from backend.api.chat_api import (
    pipeline
)

def open_recorder():

    return (
        gr.update(visible=True),      # Audio 컴포넌트 표시
        gr.update(visible=True),      # 저장 버튼 표시
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

def run_voice_chat(
    audio_path,
    session_id,
    voice_id
):
    if not voice_id :
        voice_id = "default"  
    
    print("audio_path =", audio_path)
    print("session_id =", session_id)
    print("voice_id =", voice_id)
    
    if not audio_path:
        raise Exception(
            "audio_path is None"
        )

    result = (
        pipeline.run(
            session_id=session_id,
            audio_path=audio_path,
            voice=voice_id
        )
    )

    history = [

        {
            "role": "user",
            "content": "[음성 입력]"
        },

        {
            "role": "assistant",
            "content": result["text"]
        }
    ]

    return (
        history,
        result["audio"]
    )