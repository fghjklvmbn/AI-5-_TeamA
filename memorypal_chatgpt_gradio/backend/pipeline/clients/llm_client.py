from openai import OpenAI


class LLMClient:

    def __init__(
        self,
        base_url: str,
        api_key: str = "lm-studio"
    ):

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

    def generate(
        self,
        text: str
    ):

        response = self.client.chat.completions.create(
            model="unsloth/qwen3.5-9b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 MemoryPal AI 비서다."
                    )
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.7
        )

        answer = (
            response.choices[0]
            .message.content
        )

        return {
            "answer": answer
        }