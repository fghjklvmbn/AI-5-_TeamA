import gradio as gr

from frontend.pages.chat.events import (
    create_new_session,
    select_session
)
from frontend.services.voice_service import (
    VoiceService
)


def chat_page():

    session_state = gr.State(
        value=None
    )

    with gr.Column():

        new_chat_btn = gr.Button(
            "➕ 새 채팅"
        )

        session_list = gr.Dropdown(
            choices=[],
            label="채팅 목록",
            interactive=True
        )

        chatbot = gr.Chatbot(
            value=[],
            height=550,
            label="MemoryPal Chat"
        )

        response_audio = gr.Audio(
            label="음성 응답"
        )

        with gr.Row():

            message = gr.Textbox(
                placeholder="메시지를 입력하세요...",
                scale=8
            )

            voice_selector = gr.Dropdown(
                label="응답 음성",
                choices=VoiceService.get_voice_choices(),
                interactive=True
            )

            send_btn = gr.Button(
                "전송",
                scale=1
            )

    new_chat_btn.click(
        fn=create_new_session,

        outputs=[
            session_state,
            session_list,
            chatbot
        ]
    )

    session_list.change(
        fn=select_session,

        inputs=session_list,

        outputs=[
            session_state,
            chatbot,
            response_audio
        ]
    )

    return (
        session_state,
        session_list,
        voice_selector,
        chatbot,
        message,
        send_btn,
        response_audio
    )