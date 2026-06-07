import gradio as gr

from .events import save_recording


def home_page():

    with gr.Column():

        with gr.Row():

            gr.Button(
                "☰",
                scale=0
            )

        gr.Markdown(
            "# MemoryPal"
        )

        audio_input = gr.Audio(
            sources=["microphone"],
            type="filepath",
            label="음성 녹음"
        )

        voice_selector = gr.Dropdown(
            ["기본 음성"],
            value="기본 음성",
            label="음성 선택"
        )

        save_btn = gr.Button(
            "저장"
        )

        status_box = gr.Textbox(
            label="상태",
            value="대기중"
        )

        save_btn.click(
            fn=save_recording,
            inputs=audio_input,
            outputs=status_box
        )