import gradio as gr
import whisper

# 1. Whisper 모델 로드 ("base" 모델 설정)
# 속도를 더 높이고 싶다면 "tiny", 정확도를 높이고 싶다면 "small"이나 "medium"으로 변경 가능합니다.
model = whisper.load_model("turbo", device="cpu")

def transcribe_audio(audio_file_path):
    # 녹음된 파일이 없는 경우 예외 처리
    if audio_file_path is None:
        return "오디오 파일이 없습니다. 다시 녹음해 주세요."
    
    print(f"🎬 음성 파일 처리 시작: {audio_file_path}")
    
    # 2. 저장된 파일 경로를 Whisper에 통째로 전달
    # language="ko"를 지정하여 한국어 인식률을 높입니다.
    result = model.transcribe(audio_file_path, fp16=False, language="ko")
    
    # 3. 받아쓰기 완료된 텍스트 반환
    return result["text"]

# 4. Gradio 인터페이스 구성
with gr.Blocks() as demo:
    gr.Markdown("# 🎙️ Whisper 녹음본 파일 기반 음성 인식 (STT)")
    gr.Markdown("마이크로 녹음을 진행한 뒤 **[Stop Recording]**을 누르고, **[텍스트 변환하기]** 버튼을 클릭하세요.")
    
    with gr.Row():
        with gr.Column():
            # 사용자가 녹음하거나 파일을 업로드할 수 있는 오디오 컴포넌트
            # streaming=False로 설정하여 완성된 파일 형태로 받습니다.
            audio_input = gr.Audio(
                sources="microphone", 
                type="filepath", 
                label="음성 녹음 및 업로드"
            )
            submit_btn = gr.Button("🔮 텍스트 변환하기", variant="primary")
            
        with gr.Column():
            # 결과물 출력창
            text_output = gr.Textbox(
                label="인식된 결과 텍스트", 
                lines=5, 
                placeholder="여기에 변환된 결과가 표시됩니다..."
            )

    # 버튼을 클릭했을 때 변환 함수 실행
    submit_btn.click(
        fn=transcribe_audio,
        inputs=audio_input,
        outputs=text_output
    )

# 실행 및 공유 링크 생성
demo.launch(share=True)