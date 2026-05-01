from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
import os
import re

import requests

from lmit.config import MarkItDownConfig


DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/api"

_DATA_URL_PATTERN = re.compile(
    r"^data:(?P<mime>[^;]+);base64,(?P<data>[A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MarkItDownLlmRuntime:
    client: object
    model: str
    prompt: str | None


@dataclass(frozen=True)
class _ImageInput:
    mime_type: str
    data_base64: str


@dataclass(frozen=True)
class _ChatTurn:
    role: str
    texts: tuple[str, ...]
    images: tuple[_ImageInput, ...]


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        session: requests.Session,
        timeout_seconds: float,
    ):
        self._base_url = _openai_chat_url(base_url)
        self._api_key = api_key
        self._session = session
        self._timeout_seconds = timeout_seconds
        self.chat = _OpenAICompatibleChat(self)


class _OpenAICompatibleChat:
    def __init__(self, parent: OpenAICompatibleClient):
        self.completions = _OpenAICompatibleCompletions(parent)


class _OpenAICompatibleCompletions:
    def __init__(self, parent: OpenAICompatibleClient):
        self._parent = parent

    def create(self, *, model: str, messages: list[dict[str, Any]]):
        response = self._parent._session.post(
            self._parent._base_url,
            headers={
                "Authorization": f"Bearer {self._parent._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages},
            timeout=self._parent._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = _extract_openai_message_content(payload)
        return _openai_style_response(content)


class GeminiClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        session: requests.Session,
        timeout_seconds: float,
    ):
        self._base_url = _normalize_base_url(base_url, DEFAULT_GEMINI_BASE_URL)
        self._api_key = api_key
        self._session = session
        self._timeout_seconds = timeout_seconds
        self.chat = _GeminiChat(self)


class _GeminiChat:
    def __init__(self, parent: GeminiClient):
        self.completions = _GeminiCompletions(parent)


class _GeminiCompletions:
    def __init__(self, parent: GeminiClient):
        self._parent = parent

    def create(self, *, model: str, messages: list[dict[str, Any]]):
        turns = _normalize_chat_messages(messages)
        system_instruction = _gemini_system_instruction(turns)
        contents = [_gemini_content(turn) for turn in turns if turn.role != "system"]
        if not contents:
            raise RuntimeError("Gemini provider requires at least one non-system message.")

        payload: dict[str, Any] = {"contents": contents}
        if system_instruction is not None:
            payload["system_instruction"] = system_instruction

        response = self._parent._session.post(
            _gemini_generate_content_url(self._parent._base_url, model),
            headers={
                "x-goog-api-key": self._parent._api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._parent._timeout_seconds,
        )
        response.raise_for_status()
        content = _extract_gemini_text(response.json())
        return _openai_style_response(content)


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        session: requests.Session,
        timeout_seconds: float,
    ):
        self._base_url = _normalize_base_url(base_url, DEFAULT_OLLAMA_BASE_URL)
        self._session = session
        self._timeout_seconds = timeout_seconds
        self.chat = _OllamaChat(self)


class _OllamaChat:
    def __init__(self, parent: OllamaClient):
        self.completions = _OllamaCompletions(parent)


class _OllamaCompletions:
    def __init__(self, parent: OllamaClient):
        self._parent = parent

    def create(self, *, model: str, messages: list[dict[str, Any]]):
        turns = _normalize_chat_messages(messages)
        payload = {
            "model": model,
            "messages": [_ollama_message(turn) for turn in turns],
            "stream": False,
        }
        response = self._parent._session.post(
            _ollama_chat_url(self._parent._base_url),
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=self._parent._timeout_seconds,
        )
        response.raise_for_status()
        content = _extract_ollama_text(response.json())
        return _openai_style_response(content)


def build_markitdown_llm_runtime(
    cfg: MarkItDownConfig,
    *,
    session: requests.Session,
    timeout_seconds: float,
) -> MarkItDownLlmRuntime | None:
    if not cfg.llm_enabled:
        return None

    provider = _normalize_provider(cfg.llm_provider)
    model = _require_model(cfg)
    prompt = (cfg.llm_prompt or "").strip() or None

    if provider == "openai_compatible":
        client = OpenAICompatibleClient(
            base_url=_base_url_for_provider(cfg, provider),
            api_key=_require_api_key(cfg),
            session=session,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "gemini":
        client = GeminiClient(
            base_url=_base_url_for_provider(cfg, provider),
            api_key=_require_api_key(cfg),
            session=session,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "lm_studio":
        client = OpenAICompatibleClient(
            base_url=_base_url_for_provider(cfg, provider),
            api_key=_optional_api_key(cfg) or "lm-studio",
            session=session,
            timeout_seconds=timeout_seconds,
        )
    elif provider == "ollama":
        client = OllamaClient(
            base_url=_base_url_for_provider(cfg, provider),
            session=session,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise RuntimeError(
            f"Unsupported MarkItDown LLM provider: {cfg.llm_provider!r}. "
            "Supported providers: openai_compatible, gemini, lm_studio, ollama."
        )

    return MarkItDownLlmRuntime(client=client, model=model, prompt=prompt)


def _normalize_provider(provider: str) -> str:
    text = provider.strip().lower()
    if text in {"openai_compatible", "gemini", "lm_studio", "ollama"}:
        return text
    raise RuntimeError(
        f"Unsupported MarkItDown LLM provider: {provider!r}. "
        "Supported providers: openai_compatible, gemini, lm_studio, ollama."
    )


def _require_model(cfg: MarkItDownConfig) -> str:
    model = (cfg.llm_model or "").strip()
    if not model:
        raise RuntimeError(
            "MarkItDown image LLM is enabled but llm_model is empty. "
            "Set [markitdown].llm_model in your TOML or GUI settings."
        )
    return model


def _require_api_key(cfg: MarkItDownConfig) -> str:
    api_key = _optional_api_key(cfg)
    if api_key:
        return api_key
    env_name = (cfg.llm_api_key_env or "").strip() or "<empty>"
    raise RuntimeError(
        "MarkItDown image LLM is enabled but the configured API key environment "
        f"variable is empty: {env_name}"
    )


def _optional_api_key(cfg: MarkItDownConfig) -> str | None:
    env_name = (cfg.llm_api_key_env or "").strip()
    if not env_name:
        return None
    api_key = os.environ.get(env_name, "").strip()
    return api_key or None


def _base_url_for_provider(cfg: MarkItDownConfig, provider: str) -> str:
    base_url = (cfg.llm_base_url or "").strip()
    if base_url:
        return base_url
    if provider == "openai_compatible":
        return DEFAULT_OPENAI_COMPATIBLE_BASE_URL
    if provider == "gemini":
        return DEFAULT_GEMINI_BASE_URL
    if provider == "lm_studio":
        return DEFAULT_LM_STUDIO_BASE_URL
    return DEFAULT_OLLAMA_BASE_URL


def _normalize_base_url(base_url: str, default: str) -> str:
    text = (base_url or "").strip()
    return (text or default).rstrip("/")


def _normalize_chat_messages(messages: list[dict[str, Any]]) -> list[_ChatTurn]:
    turns: list[_ChatTurn] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower() or "user"
        raw_content = message.get("content")
        if isinstance(raw_content, str):
            texts = (raw_content,)
            images: tuple[_ImageInput, ...] = ()
        else:
            texts_list: list[str] = []
            images_list: list[_ImageInput] = []
            for item in raw_content or []:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip().lower()
                if item_type == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        texts_list.append(text)
                elif item_type == "image_url":
                    image_url_value = item.get("image_url")
                    image_url = (
                        image_url_value.get("url")
                        if isinstance(image_url_value, dict)
                        else image_url_value
                    )
                    if isinstance(image_url, str):
                        images_list.append(_parse_data_url_image(image_url))
            texts = tuple(texts_list)
            images = tuple(images_list)
        turns.append(_ChatTurn(role=role, texts=texts, images=images))
    return turns


def _parse_data_url_image(url: str) -> _ImageInput:
    match = _DATA_URL_PATTERN.match(url.strip())
    if not match:
        raise RuntimeError(
            "This LLM provider only supports data: image URLs from MarkItDown image input."
        )
    return _ImageInput(
        mime_type=match.group("mime").strip(),
        data_base64="".join(match.group("data").split()),
    )


def _gemini_system_instruction(turns: list[_ChatTurn]) -> dict[str, Any] | None:
    parts: list[dict[str, str]] = []
    for turn in turns:
        if turn.role != "system":
            continue
        for text in turn.texts:
            if text.strip():
                parts.append({"text": text})
    if not parts:
        return None
    return {"parts": parts}


def _gemini_content(turn: _ChatTurn) -> dict[str, Any]:
    role = "model" if turn.role == "assistant" else "user"
    parts: list[dict[str, Any]] = []
    for text in turn.texts:
        if text.strip():
            parts.append({"text": text})
    for image in turn.images:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image.mime_type,
                    "data": image.data_base64,
                }
            }
        )
    if not parts:
        parts.append({"text": ""})
    return {"role": role, "parts": parts}


def _ollama_message(turn: _ChatTurn) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant" if turn.role == "assistant" else "user",
        "content": "\n\n".join(text for text in turn.texts if text.strip()),
    }
    if turn.images:
        payload["images"] = [image.data_base64 for image in turn.images]
    return payload


def _extract_openai_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("invalid OpenAI-compatible response: missing choices[0]")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("invalid OpenAI-compatible response: missing message")

    return _extract_openai_content_value(message.get("content"))


def _extract_openai_content_value(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)
    raise RuntimeError("invalid OpenAI-compatible response: missing message content")


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("invalid Gemini response: missing candidates[0]")
    content = candidates[0].get("content")
    if not isinstance(content, dict):
        raise RuntimeError("invalid Gemini response: missing content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise RuntimeError("invalid Gemini response: missing content.parts")
    texts = [
        part.get("text")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        raise RuntimeError("invalid Gemini response: missing text parts")
    return "\n".join(texts)


def _extract_ollama_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    response = payload.get("response")
    if isinstance(response, str):
        return response
    raise RuntimeError("invalid Ollama response: missing message.content")


def _openai_style_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _openai_chat_url(base_url: str) -> str:
    normalized = _normalize_base_url(base_url, DEFAULT_OPENAI_COMPATIBLE_BASE_URL)
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def _gemini_generate_content_url(base_url: str, model: str) -> str:
    normalized = _normalize_base_url(base_url, DEFAULT_GEMINI_BASE_URL)
    if normalized.endswith("/models"):
        return normalized + f"/{model}:generateContent"
    return normalized + f"/models/{model}:generateContent"


def _ollama_chat_url(base_url: str) -> str:
    normalized = _normalize_base_url(base_url, DEFAULT_OLLAMA_BASE_URL)
    if normalized.endswith("/chat"):
        return normalized
    if normalized.endswith("/api"):
        return normalized + "/chat"
    return normalized + "/api/chat"
