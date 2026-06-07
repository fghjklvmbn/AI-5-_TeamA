# frontend/pages/chat/page.py

# import gradio as gr

# history = [
#     gr.ChatMessage(role="assistant", content="How can I help you?"),
#     gr.ChatMessage(role="user", content="Can you make me a plot of quarterly sales?"),
#     gr.ChatMessage(role="assistant", content="I am happy to provide you that report and plot.")
# ]

# def chat_page():

#     # 구조변경(예시 내용)
#     chatbot = gr.Chatbot(history)

#     gr.Textbox(
#         placeholder="메시지 입력"
#     )

# frontend/pages/chat/page.py

import gradio as gr


def chat_page():

    chatbot = gr.Chatbot(
        value=[
            {
                "role": "assistant",
                "content": "안녕하세요. MemoryPal입니다."
            }
        ],
        height=550,
        label="MemoryPal Chat"
    )

    message = gr.Textbox(
        placeholder="메시지를 입력하세요..."
    )

    send_btn = gr.Button("전송")

    return chatbot, message, send_btn