import gradio as gr
from .events import get_idle_state
from frontend.pages.home.events import (
    open_recorder,
    save_record
)

def home_page():

    with gr.Column(
        elem_classes=["page-container"]
    ):

        with gr.Row():

            menu_btn = gr.Button(
                "☰",
                scale=0
            )

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

        save_btn = gr.Button(
            "녹음 저장",
            visible=False
        )

        latest_record = gr.Textbox(
            label="최근 녹음",
            value="없음",
            interactive=False
        )

        gr.Markdown(
            "## 시작하기"
        )

        voice_selector = gr.Dropdown(
            choices=[
                "기본 음성"
            ],
            value="기본 음성"
        )

        status_box = gr.Textbox(
            value=get_idle_state(),
            interactive=False,
            elem_classes=["status-box"]
        )

        latest_record = gr.Textbox(
            label="최근 녹음",
            value="없음",
            interactive=False
        )

        return (
            mic_btn,
            audio_input,
            save_btn,
            voice_selector,
            status_box,
            latest_record
        )
