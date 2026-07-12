import gradio as gr
import whisper
import numpy as np

# Whisper 모델 로드 ("tiny"는 cpu에서도 가볍게 돌아갑니다)
model = whisper.load_model("tiny", device="cpu")

def transcribe(stream, new_chunk):
    if new_chunk is None:
        return stream, ""
        
    sample_rate, audio_data = new_chunk
    
    # 정형화: 오디오 데이터를 float32 타입으로 변경하고 정규화(-1.0 ~ 1.0)
    if audio_data.dtype == np.int16:
        audio_data = audio_data.astype(np.float32) / 32768.0
    elif audio_data.dtype == np.int32:
        audio_data = audio_data.astype(np.float32) / 2147483648.0

    # 채널이 여러 개(스테레오)라면 모노로 변환
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)

    # 기존에 들어온 오디오 데이터 뒤에 새로 들어온 조각을 붙입니다.
    if stream is None:
        stream = audio_data
    else:
        stream = np.concatenate((stream, audio_data))

    result = model.transcribe(stream, fp16=False)
    
    return stream, result["text"]

gr.Interface(
    fn=transcribe,
    inputs=[
        "state", gr.Audio(sources=["microphone"], type="numpy", streaming=True),
    ],
    outputs=[
        "state", "text",
    ],
    live=True
).launch(share=True)