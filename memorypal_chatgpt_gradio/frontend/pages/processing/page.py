# frontend/pages/processing/page.py

import gradio as gr


def processing_page():

    with gr.Column(
        visible=False
    ) as processing_view:

        gr.HTML(
            """
            <div style="
                display:flex;
                flex-direction:column;
                justify-content:center;
                align-items:center;
                height:70vh;
            ">

                <div class="loader"></div>

                <h2>
                    잠시만 기다려주세요
                </h2>

                <p>
                    AI가 답변을 생성중입니다.
                </p>

            </div>
            """
        )

    return processing_view