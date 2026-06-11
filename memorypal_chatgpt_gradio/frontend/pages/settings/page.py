import gradio as gr


def settings_page():

    gr.Markdown("# 설정")

    gr.Slider(
        minimum=0.5,
        maximum=3.0,
        value=1.0,
        label="톤"
    )

    gr.Slider(
        minimum=0.5,
        maximum=3.0,
        value=1.0,
        label="피치"
    )