import gradio as gr

from frontend.pages.chat.events import (
    create_new_session,
    select_session,
    select_message
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
        message_selector = gr.Dropdown(
            label="이전 음성 응답",
            choices=[],
            interactive=True
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
            chatbot,
            response_audio,
            message_selector
        ]
    )

    message_selector.change(
        fn=select_message,

        inputs=message_selector,

        outputs=response_audio
    )
    # send_btn.click(
    #     fn=send_message,

    #     inputs=[
    #         message,
    #         chatbot,
    #         session_state,
    #     ],

    #     outputs=[
    #         chatbot,
    #         message
    #     ]
    # )

    return (
        session_state,
        session_list,
        chatbot,
        message_selector,
        message,
        send_btn,
        response_audio
    )