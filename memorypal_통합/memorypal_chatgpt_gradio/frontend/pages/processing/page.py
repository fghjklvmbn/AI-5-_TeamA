import gradio as gr

def processing_page():

    with gr.Column():

        gr.Markdown(
            """
            # MemoryPal

            ### 음성을 분석하고 있습니다...
            """
        )

        gr.HTML(
            """
            <div style="
                display:flex;
                justify-content:center;
                align-items:center;
                padding:40px;
            ">
                <div class="spinner"></div>
            </div>

            <style>
            .spinner {
                width:80px;
                height:80px;

                border:8px solid #ddd;
                border-top:8px solid #4f46e5;

                border-radius:50%;

                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                from {
                    transform: rotate(0deg);
                }
                to {
                    transform: rotate(360deg);
                }
            }
            </style>
            """
        )