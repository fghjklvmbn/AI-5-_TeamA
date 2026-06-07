import gradio as gr

from pathlib import Path
from frontend.pages.home.page import home_page
from frontend.pages.chat.page import chat_page
from frontend.pages.settings.page import settings_page
from frontend.pages.voice_manager.page import voice_page

path = Path.cwd()
print(path)
# CSS = [
#     Path("frontend/components/styles.css").read_text(),
#     # Path("frontend/components/mobile.css").read_text(),
#     # Path("frontend/components/theme.css").read_text(),
# ]

def show_home():
    return (
        gr.update(visible=True),
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
    )


def show_voice():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(visible=False),
    )


def show_settings():
    return (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True),
    )

# css=CSS 포함
with gr.Blocks( title="MemoryPal") as demo:

    with gr.Column():

        with gr.Column(visible=True) as home_view:
            home_page()

        with gr.Column(visible=False) as chat_view:
            chat_page()

        with gr.Column(visible=False) as voice_view:
            voice_page()

        with gr.Column(visible=False) as settings_view:
            settings_page()

        with gr.Row():

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

demo.launch(
    # css=CSS,
    share=True
)