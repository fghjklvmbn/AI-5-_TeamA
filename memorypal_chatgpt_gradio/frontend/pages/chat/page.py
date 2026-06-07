import gradio as gr

from frontend.pages.chat.events import (
    create_new_session,
    send_message,
    select_session
)


def chat_page():

    session_state = gr.State(
        value=None
    )

    with gr.Column():

        new_chat_btn = gr.Button(
            "➕ 새 채팅"
        )

        session_list = gr.Radio(
            choices=[],
            label="채팅 목록"
        )

        chatbot = gr.Chatbot(
            value=[],
            height=550,
            label="MemoryPal Chat"
        )

        with gr.Row():

            message = gr.Textbox(
                placeholder="메시지를 입력하세요...",
                scale=8
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
            chatbot
        ]
    )

    send_btn.click(
        fn=send_message,

        inputs=[
            message,
            chatbot,
            session_state
        ],

        outputs=[
            chatbot,
            message
        ]
    )

    return (
        session_state,
        session_list,
        chatbot,
        message,
        send_btn
    )