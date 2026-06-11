import gradio as gr

from frontend.pages.voice_manager.events import (
    register_voice,
    load_voice_list,
    select_voice
)


def voice_page():

    with gr.Column():

        gr.Markdown(
            "## 음성관리"
        )

        voice_name = gr.Textbox(
            label="음성 이름"
        )

        audio_upload = gr.Audio(
            type="filepath",
            label="음성 업로드"
        )

        register_btn = gr.Button(
            "➕ 개인 음성 추가"
        )

        refresh_btn = gr.Button(
            "🔄 목록 새로고침"
        )

        status = gr.Textbox(
            label="상태",
            interactive=False
        )

        voice_list = gr.Radio(
            choices=[],
            label="등록된 음성"
        )
        
        voice_state = gr.State(
            value=None
        )

        voice_list.change(
            fn=select_voice,
            inputs=voice_list,
            outputs=voice_state
        )

        register_btn.click(
            fn=register_voice,

            inputs=[
                voice_name,
                audio_upload
            ],
            outputs=status
        )

        refresh_btn.click(
            fn=load_voice_list,
            outputs=voice_list
        )

    return (
        voice_state,
        voice_name,
        audio_upload,
        register_btn,
        voice_list
    )