import gradio as gr
import torch
import torchaudio
import soundfile as sf
import os
from transformers import AutoModelForCausalLM, AutoProcessor

# 1. 공식 가이드라인: Voice Clone은 CustomVoice가 아닌 Base/Instruct 모델을 사용합니다.
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"  # 혹은 "Qwen/Qwen3-TTS-12Hz-0.6B-Base" (저사양용)
device = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Loading Qwen3-TTS Processor & Model: {MODEL_ID} on {device}...")
# 오디오와 텍스트 입력을 멀티모달 토큰으로 처리하는 공식 프로세서
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
    device_map="auto" if device == "cuda" else None
)
print("Qwen3-TTS Model loaded successfully for Voice Cloning!")


def voice_clone_wrapper(target_text, language, ref_audio_path, ref_text, mode):
    """
    Qwen3-TTS 공식 깃허브의 Voice Clone 인터페이스 규격을 따르는 함수
    """
    if not target_text.strip():
        return None, "합성할 대상 텍스트를 입력해주세요."
    if not ref_audio_path:
        return None, "복제할 참조 음성(.wav) 파일을 업로드해주세요."
        
    try:
        # 1. 참조 오디오 로드 (torchaudio 규격 호환)
        ref_audio, sr = torchaudio.load(ref_audio_path)
        
        # 2. 공식 프로세서 데이터 가공 (타겟 텍스트, 참조 오디오, 옵션인 참조 텍스트 통합)
        # 팁: ref_text를 제공하면 음성 복제 유사도와 발음 정확도가 비약적으로 상승합니다.
        processing_kwargs = {
            "text": target_text,
            "audio": ref_audio,
            "sampling_rate": sr,
            "return_tensors": "pt"
        }
        
        # 사용자가 참조 텍스트(대사)를 적었을 경우에만 추가 파라미터 전달
        if ref_text and ref_text.strip():
            processing_kwargs["ref_text"] = ref_text.strip()
            
        inputs = processor(**processing_kwargs).to(device)
        
        # 3. 모델 오디오 생성 가이드라인 반영 (max_new_tokens 제어)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=2048)
            
        # 4. 토큰을 다시 오디오 파동으로 디코딩
        cloned_audio = processor.decode(output[0])
        
        # 5. 임시 파일로 최종 저장 (Qwen3-TTS 표준 출력 속도인 24000Hz 혹은 모델 기본 샘플레이트)
        output_filename = "output_qwen3_cloned.wav"
        torchaudio.save(output_filename, cloned_audio.unsqueeze(0).cpu(), sample_rate=24000)
        
        return output_filename, "🎉 성공적으로 목소리가 복제 및 합성되었습니다!"
        
    except Exception as e:
        return None, f"오류가 발생했습니다: {str(e)}"


# --- Qwen3-TTS 공식 스페이스 스타일 Gradio UI 구성 ---
with gr.Blocks(title="Qwen3-TTS Voice Clone Studio") as demo:
    gr.Markdown("## 🎙️ Qwen3-TTS 공식 규격 Voice Clone 플레이그라운드")
    gr.Markdown("단 3~10초의 참조 음성 샘플만으로 타겟 언어와 목소리를 똑같이 복제(Zero-shot)합니다.")
    
    with gr.Row():
        # 왼쪽: 입력 조건 설정
        with gr.Column():
            gr.Markdown("### 🎛️ 입력 설정 (Inputs)")
            
            target_text_input = gr.Textbox(
                label="Target Text (새로 출력할 대사)", 
                placeholder="여기에 AI 목소리로 말하게 하고 싶은 문장을 입력하세요.", 
                lines=3
            )
            
            language_dropdown = gr.Dropdown(
                choices=["Korean", "English", "Chinese", "Japanese", "German", "French", "Spanish", "Italian"],
                value="Korean",
                label="출력 언어 (Language)"
            )
            
            gr.HTML("<hr style='border-top: 1px dashed #bbb;'>")
            
            ref_audio_input = gr.Audio(
                label="Reference Audio (복제할 원본 목소리 파일)",
                type="filepath"
            )
            
            ref_text_input = gr.Textbox(
                label="Reference Text (참조 오디오의 실제 대사 - 선택 권장)",
                placeholder="녹음 파일 속 사람이 말하는 내용을 받아적어 주시면 싱크로율이 극대화됩니다.",
                lines=2
            )
            
            submit_btn = gr.Button("Clone & Generate (목소리 복제 및 생성)", variant="primary")
            
        # 오른쪽: 생성 결과 출력
        with gr.Column():
            gr.Markdown("### 🔊 생성 결과 (Outputs)")
            audio_output = gr.Audio(label="Cloned AI Voice (복제 완료된 음성)", type="filepath")
            status_output = gr.Textbox(label="System Status (시스템 상태)", interactive=False)

    # 이벤트 바인딩
    submit_btn.click(
        fn=voice_clone_wrapper,
        inputs=[
            target_text_input, 
            language_dropdown, 
            ref_audio_input, 
            ref_text_input
        ],
        outputs=[audio_output, status_output]
    )

if __name__ == "__main__":
    demo.launch(share=True)