import whisper
import services.transcription_service as transcription
from pathlib import Path

model_transcript = transcription.TranscriptionService()
local_path = Path.cwd()
local_path = str(local_path)
print(local_path+"\\uploads\\test.wav")

model = whisper.load_model(
    "turbo"
)

result = model_transcript.transcribe(
    audio_path="/Users/dsapo.PC/Documents/AI-5-_TeamA/STT_backend_server/uploads/test.wav",
    # language="ko"
)

print(
    result["text"]
)