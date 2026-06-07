import gradio as gr


def voice_page():

    gr.Markdown("## 음성관리")

    gr.Button(
        "➕ 개인 음성 추가"
    )

    gr.Radio(
        choices=[],
        label="등록된 음성"
    )