import gradio as gr
from .events import get_idle_state
from frontend.pages.home.events import (
    open_recorder,
    save_record,
)

from frontend.services.voice_service import (
    VoiceService
)

def home_page():

    with gr.Column(
        elem_classes=["page-container"]
    ):

        mic_btn = gr.Button(
            "🎤",
            elem_id="mic-button"
        )

        audio_input = gr.Audio(
            sources=["microphone"],
            type="filepath",
            visible=False,
            label="음성 녹음"
        )

        voice_selector = gr.Dropdown(
            label="응답 음성",
            choices=VoiceService.get_voice_choices(),
            interactive=True
        )

        # 파이프라인 연결점. 채팅으로 바꿈
        save_btn = gr.Button(
            "채팅",
            visible=False
        )

        return (
            mic_btn,
            audio_input,
            voice_selector,
            save_btn
        )
