"""LLM 客户端抽象基类。"""


class LLMClient:
    def __init__(self, model: str = "", temperature: float = 0.3, max_tokens: int = 2048):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
