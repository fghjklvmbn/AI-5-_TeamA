import gradio as gr
import torch
import soundfile as sf
import os

# Hugging Face 공식 문서의 모델 로드 표준 패턴 기반
# (실제 qwen3-tts 패키지 구조에 따라 모델 클래스명은 변경될 수 있습니다)
try:
    from qwen_tts import Qwen3TTSModel
except ImportError:
    # 예시를 위한 가상 임포트 처리 (실제 환경에 맞게 패키지 확인 필요)
    raise ImportError("qwen-tts 라이브러리가 설치되어 있는지 확인해주세요.")

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Loading model: {MODEL_ID} on {device}...")
# Hugging Face 문서 기반 가이드라인: bfloat16 및 flash_attention_2 활용 권장
model = Qwen3TTSModel.from_pretrained(
    MODEL_ID,
    device_map=device,
    dtype=torch.bfloat16 if device == "cuda" else torch.float32,
    attn_implementation="flash_attention_2" if device == "cuda" else "sdpa"
)
print("Model loaded successfully!")

def tts_generation_wrapper(text, language, speaker, instruct):
    """
    Hugging Face CustomVoice 모델의 공식 인풋 구조를 처리하는 함수입니다.
    """
    if not text.strip():
        return None, "텍스트를 입력해주세요."
    
    try:
        # 모델의 공식 Custom Voice 생성 메서드 호출
        # 리턴 형태: (wav_tensor, sample_rate)
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            instruct=instruct if instruct.strip() else None
        )
        
        # Gradio 오디오 출력을 위해 임시 파일로 저장 (또는 numpy array로 직접 전달 가능)
        output_filename = "output_qwen3_tts.wav"
        # 단일 화자 생성이므로 첫 번째 배치 결과[0]를 저장합니다.
        sf.write(output_filename, wavs[0], sr)
        
        return output_filename, "음성 합성이 완료되었습니다!"
    except Exception as e:
        return None, f"오류가 발생했습니다: {str(e)}"

# --- Gradio UI 구성 (Hugging Face Blocks 표준 양식) ---
with gr.Blocks(title="Qwen3-TTS 1.7B CustomVoice WebUI") as demo:
    gr.Markdown(f"## 🎙️ Qwen3-TTS-12Hz-1.7B-CustomVoice 플레이그라운드")
    gr.Markdown("Hugging Face 공식 모델 사양에 맞춘 맞춤형 내장 음색 및 스타일 지정 TTS 인터페이스입니다.")
    
    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(
                label="합성할 텍스트", 
                placeholder="안녕하세요, 반갑습니다! 생성할 문장을 입력하세요.", 
                lines=3
            )
            
            language_dropdown = gr.Dropdown(
                choices=["Korean", "English", "Chinese", "Japanese", "German", "French", "Spanish"],
                value="Korean",
                label="언어 설정 (Language)"
            )
            
            speaker_dropdown = gr.Dropdown(
                choices=["Sohee", "Serena", "Uncle Fu", "Vivian", "Ryan"],
                value="Sohee",
                label="프리미엄 보이스 선택 (Speaker)"
            )
            
            instruct_input = gr.Textbox(
                label="스타일/감정 지시문 (Instruction)",
                placeholder="예: 매우 기쁜 목소리로, 슬픈 어조로, 속삭이듯이 (공백 시 기본값)",
                value=""
            )
            
            submit_btn = gr.Button("음성 생성하기", variant="primary")
            
        with gr.Column():
            audio_output = gr.Audio(label="생성된 음성", type="filepath")
            status_output = gr.Textbox(label="시스템 상태", interactive=False)

    # 이벤트 연결
    submit_btn.click(
        fn=tts_generation_wrapper,
        inputs=[text_input, language_dropdown, speaker_dropdown, instruct_input],
        outputs=[audio_output, status_output]
    )

if __name__ == "__main__":
    # 외부 접근이 필요하면 share=True로 설정하세요.
    demo.launch(share=True)