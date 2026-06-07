import whisper

model = whisper.load_model(
    "turbo"
)

result = model.transcribe(
    "test.wav",
    language="ko"
)

print(
    result["text"]
)