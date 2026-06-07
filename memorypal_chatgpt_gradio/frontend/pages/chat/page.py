# frontend/pages/chat/page.py

import gradio as gr

history = [
    gr.ChatMessage(role="assistant", content="How can I help you?"),
    gr.ChatMessage(role="user", content="Can you make me a plot of quarterly sales?"),
    gr.ChatMessage(role="assistant", content="I am happy to provide you that report and plot.")
]

def chat_page():

    # 구조변경(예시 내용)
    chatbot = gr.Chatbot(history)

    gr.Textbox(
        placeholder="메시지 입력"
    )