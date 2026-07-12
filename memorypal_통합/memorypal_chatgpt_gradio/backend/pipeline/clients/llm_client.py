from openai import OpenAI


class LLMClient:

    def __init__(
        self,
        base_url: str,
        api_key: str = "lm-studio"
    ):

        self.base_url = base_url

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

    def generate(
        self,
        text: str
    ):

        response = self.client.chat.completions.create(
            model="llama-3.2-korean-bllossom-3b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        """너는 MemoryPal AI 비서다. 메모리팔은 사용자에게 친근하게 대화하며 기억을 하기 위한 플랫폼이니 답변 스타일을 여기에 맞추도록 한다.
                        답변할때는 최대한 50~100자로 요약하여 사용자에게 답변한다. 답변할때 항상 친근한 말투로 말한다, 모든 답변을 구어체로 답변한다. 내용이 매끄럽게 되도록 한다."""
                    )
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            temperature=0.7,
        )

        answer = (
            response.choices[0]
            .message.content
        )

        return {
            "answer": answer
        }