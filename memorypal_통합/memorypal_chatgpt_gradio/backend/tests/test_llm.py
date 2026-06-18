import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

sys.path.append(
    str(ROOT_DIR)
)

from backend.pipeline.clients.llm_client import (
    LLMClient
)


def main():

    llm = LLMClient(
        base_url="http://192.168.2.41:1234/v1"
    )

    result = llm.generate(
        "안녕?"
    )

    print(result)


if __name__ == "__main__":
    main()