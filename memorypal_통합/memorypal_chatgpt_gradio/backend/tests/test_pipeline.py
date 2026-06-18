import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.manager import (
    PipelineManager
)

from backend.pipeline.clients.stt_client import (
    STTClient
)

from backend.pipeline.clients.llm_client import (
    LLMClient
)


def main():

    stt = STTClient(
        host="localhost",
        port=8001
    )

    llm = LLMClient(
        base_url="http://192.168.2.41:1234/v1"
    )

    pipeline = PipelineManager(
        stt_client=stt,
        llm_client=llm,
        tts_client=None
    )

    result = pipeline.run(
        audio_path="/Users/dsapo.PC/Documents/AI-5-_TeamA/memorypal_chatgpt_gradio/storage/recordings/REC_20260607_170940.wav"
    )

    print(result)


if __name__ == "__main__":
    main()