"""
=====================================================================
Toprax — AI Provider Soyutlaması (IT-32 / FAZ 11 — Integration Hub)
=====================================================================
`satellite_provider.py`/`channel_providers.py` ile AYNI ABC + factory
kalıbı. ÖNCESİNDE (IT-10/extras.py) OpenAI/Gemini/Anthropic'e yapılan
HTTP çağrıları `extras.py` içinde İKİ AYRI yerde (AI Hastalık Tespiti +
AI Copilot) neredeyse birebir TEKRARLANMIŞ halde duruyordu — roadmap'in
IT-32 kabul kriterinin işaret ettiği tam olarak bu "dağınık doğrudan
3. parti çağrısı" durumuydu (satellite/channel zaten IT-17/IT-25'te
provider pattern'e taşınmıştı, AI hiç taşınmamıştı). Bu modül o iki
tekrarı BİRLEŞTİRİR — davranış (hangi sağlayıcıya hangi payload gider)
AYNEN korunur, sadece tek bir yerde yaşar.

`integrations.py`'nin `get_ai_service_config(db)`'i (provider/api_key/
model) DEĞİŞMEDİ — extras.py hâlâ config'i oradan okur, sadece config'i
BURADAKİ `get_ai_provider()`'a geçirir.
"""
from abc import ABC, abstractmethod
from typing import Optional
import requests


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, system_prompt: str, user_text: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        raise NotImplementedError


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: Optional[str]):
        self.api_key, self.model = api_key, model

    def generate_text(self, system_prompt: str, user_text: str) -> str:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model or "gpt-4o-mini",
                  "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}]},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ]},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: Optional[str]):
        self.api_key, self.model = api_key, model

    def generate_text(self, system_prompt: str, user_text: str) -> str:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model or 'gemini-2.0-flash'}:generateContent?key={self.api_key}",
            json={"contents": [{"parts": [{"text": system_prompt + "\n\n" + user_text}]}]},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model or 'gemini-2.0-flash'}:generateContent?key={self.api_key}",
            json={"contents": [{"parts": [
                {"text": system_prompt + "\n\n" + user_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
            ]}]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: Optional[str]):
        self.api_key, self.model = api_key, model

    def generate_text(self, system_prompt: str, user_text: str) -> str:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={"model": self.model or "claude-sonnet-4-6", "max_tokens": 500,
                  "system": system_prompt, "messages": [{"role": "user", "content": user_text}]},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def generate_vision(self, system_prompt: str, user_text: str, image_b64: str) -> str:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model or "claude-sonnet-4-6", "max_tokens": 1000, "system": system_prompt,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                ]}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


_PROVIDER_CLASSES = {"openai": OpenAIProvider, "gemini": GeminiProvider, "anthropic": AnthropicProvider}


def get_ai_provider(provider: str, api_key: str, model: Optional[str] = None) -> AIProvider:
    """`satellite_provider.get_satellite_provider()`/`channel_providers.get_channel_provider()`
    ile AYNI factory kalıbı — çağıran (extras.py) hangi sınıfın örneklendiğini bilmez."""
    cls = _PROVIDER_CLASSES.get(provider)
    if cls is None:
        raise ValueError(f"Bilinmeyen AI sağlayıcısı: {provider}")
    return cls(api_key, model)
