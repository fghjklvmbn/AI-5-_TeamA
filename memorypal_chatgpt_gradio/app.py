import gradio as gr

from pathlib import Path
from frontend.pages.home.page import home_page
from frontend.pages.home.events import (
    load_session_list,
    initialize_chat,
    open_recorder,
    save_record
)

from frontend.pages.chat.page import chat_page
from frontend.pages.settings.page import settings_page
from frontend.pages.voice_manager.page import voice_page
from pathlib import Path

from frontend.pages.chat.events import (
    load_session_list
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
        gr.update(visible=False)
    )


def show_chat():
    return (
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False)
    )


def show_voice():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False)
    )


def show_settings():
    return (
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
                save_btn,
                voice_selector,
                home_status,
                latest_record
            ) = home_page()

        with gr.Column(visible=False) as chat_view:
            (
                session_state,
                session_list,
                chatbot,
                message,
                send_btn
            ) = chat_page()

        with gr.Column(visible=False) as voice_view:
            voice_page()

        with gr.Column(visible=False) as settings_view:
            settings_page()

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
            settings_view
        ]
    )

    chat_btn.click(
        show_chat,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view
        ]
    )

    voice_btn.click(
        show_voice,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view
        ]
    )

    settings_btn.click(
        show_settings,
        outputs=[
            home_view,
            chat_view,
            voice_view,
            settings_view
        ]
    )

    demo.load(
        fn=initialize_chat,

        outputs=[
            session_state,
            session_list,
            chatbot
        ]
    )

    # 마이크 버튼 클릭
    mic_btn.click(
        fn=open_recorder,
        outputs=[
            audio_input,
            save_btn,
            home_status
        ]
    )

    # 저장 버튼 클릭
    save_btn.click(
        fn=save_record,
        inputs=audio_input,
        outputs=[
            home_status,
            latest_record
        ]
    )

demo.launch(
    css=CSS,
    share=True
)