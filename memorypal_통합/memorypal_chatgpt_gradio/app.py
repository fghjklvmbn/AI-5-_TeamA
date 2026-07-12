import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

import gradio as gr

from frontend.pages.home.page import home_page
from frontend.pages.home.events import (
    open_recorder,
    run_voice_chat
)

from frontend.pages.chat.page import chat_page
from frontend.pages.chat.events import (
   initialize_chat,
   send_message,
)

from frontend.pages.settings.page import settings_page
from frontend.pages.voice_manager.page import voice_page

from frontend.pages.processing.page import (
    processing_page
)

BASE_DIR = Path(__file__).parent

CSS = "\n".join([
    (BASE_DIR / "frontend/components/CSS/styles.css")
        .read_text(encoding="utf-8"),

    (BASE_DIR / "frontend/components/CSS/mobile.css")
        .read_text(encoding="utf-8"),

    (BASE_DIR / "frontend/components/CSS/theme.css")
        .read_text(encoding="utf-8"),
])

def show_home():
    return (
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def show_chat():
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def show_voice():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def show_settings():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
    )


def show_processing():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True)
    )

# css=CSS 포함
with gr.Blocks(title="MemoryPal") as demo:

    with gr.Column():
        with gr.Column(visible=True) as home_view:
            (
                mic_btn,
                audio_input,
                voice_selector,
                save_btn
            ) = home_page()

        with gr.Column(visible=False) as chat_view:
            (
                session_state,
                session_list,
                voice_selector,
                chatbot,
                message,
                send_btn,
                response_audio
            ) = chat_page()

        with gr.Column(visible=False) as voice_view:
            (
                voice_state,
                voice_name,
                audio_upload,
                register_btn,
                voice_list
            ) = voice_page()

        with gr.Column(visible=False) as settings_view:
            settings_page()

        with gr.Column(visible=False) as processing_view:
            processing_page()

        with gr.Row(elem_classes=["bottom-nav"]):
            home_btn = gr.Button("🏠 홈")
            chat_btn = gr.Button("💬 채팅")
            voice_btn = gr.Button("🎤 음성")
            settings_btn = gr.Button("⚙ 설정")

    home_btn.click(
        show_home,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    )

    chat_btn.click(
        show_chat,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    )

    voice_btn.click(
        show_voice,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    )

    settings_btn.click(
        show_settings,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    )

    send_btn.click(
        fn=send_message,
        inputs=[
            message,
            chatbot,
            session_state,
            voice_selector
        ],
        outputs=[
            chatbot,
            message
        ]
    )

    demo.load(
        fn=initialize_chat,

        outputs=[
            session_state,
            session_list,
            chatbot,
            response_audio
        ]
    )

    # 마이크 버튼 클릭
    mic_btn.click(
        fn=open_recorder,
        outputs=[
            audio_input,
            save_btn
        ]
    )

    # 저장 버튼 클릭
    save_btn.click(
        fn=show_processing,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    ).then(
        fn=run_voice_chat,
        inputs=[
            audio_input,
            session_state,
            voice_selector
        ],
        outputs=[
            chatbot,
            response_audio
        ]
    ).then(
        fn=show_chat,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view,
            processing_view
        ]
    )

demo.launch(
    css=CSS,
    server_name="0.0.0.0",
    server_port=7860,
    share=True
)