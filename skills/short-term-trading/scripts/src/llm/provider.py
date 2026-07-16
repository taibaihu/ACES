"""多模型 LLM Provider 实现：Claude / OpenAI / DeepSeek。"""

import json as _json
import os
import re

import requests

from .base import LLMClient
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


def _utf8_text(resp: "requests.Response") -> str:
    try:
        return resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return resp.text


class ClaudeClient(LLMClient):
    def __init__(self, model="claude-sonnet-4-20250514", api_key="",
                 api_url="https://api.anthropic.com/v1/messages", temperature=0.3, max_tokens=2048):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key or os.getenv("CLAUDE_API_KEY", "")
        self.api_url = api_url

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                   "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return _json.loads(_utf8_text(resp))["content"][0]["text"]
        except Exception as e:
            logger.error(f"Claude API 失败: {e}")
            return ""


class OpenAIClient(LLMClient):
    def __init__(self, model="gpt-4o", api_key="",
                 api_url="https://api.openai.com/v1/chat/completions", temperature=0.3, max_tokens=2048):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_url = api_url

    def _clean_response(self, raw: str) -> str:
        raw = re.sub(r'\s*data:\s*\[DONE\]\s*$', '', raw.strip())
        data = _json.loads(raw)
        msg = data["choices"][0]["message"]
        return msg.get("content", "") or msg.get("reasoning_content", "")

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                   "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            return self._clean_response(_utf8_text(resp))
        except Exception as e:
            logger.error(f"OpenAI API 失败: {e}")
            return ""


class DeepSeekClient(LLMClient):
    def __init__(self, model="deepseek-chat", api_key="",
                 api_url="https://api.deepseek.com/v1/chat/completions", temperature=0.3, max_tokens=2048):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.api_url = api_url

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                   "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
        try:
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return _json.loads(_utf8_text(resp))["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"DeepSeek API 失败: {e}")
            return ""


def create_llm_client(provider: str = "") -> LLMClient:
    from ..config import config
    provider = provider or config.LLM_PROVIDER
    model = config.LLM_MODEL

    mapping = {
        "claude": lambda: ClaudeClient(model=model),
        "openai": lambda: OpenAIClient(model=model, api_url=config.OPENAI_API_URL),
        "gpt": lambda: OpenAIClient(model=model, api_url=config.OPENAI_API_URL),
        "deepseek": lambda: DeepSeekClient(model=model),
    }
    cls = mapping.get(provider.lower(), mapping["openai"])
    logger.info(f"LLM provider: {provider}, model: {model}")
    return cls()
