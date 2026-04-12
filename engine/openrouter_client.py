from __future__ import annotations

import json
from urllib import error, request
from typing import Any

from engine.llm_config import get_openrouter_config


class OpenRouterError(RuntimeError):
    pass


def chat_completion(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    response_format: dict[str, Any] | None = None,
    max_tokens: int = 500,
    temperature: float = 0.1,
    timeout: int = 60,
) -> dict[str, Any]:
    config = get_openrouter_config()
    if not config.api_key_present:
        raise OpenRouterError("OPENROUTER_API_KEY is not configured.")

    payload: dict[str, Any] = {
        "model": model or config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    if config.site_url:
        headers["HTTP-Referer"] = config.site_url
    if config.app_name:
        headers["X-OpenRouter-Title"] = config.app_name

    req = request.Request(
        url=f"{config.base_url.rstrip('/')}/chat/completions",
        headers=headers,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise OpenRouterError(f"OpenRouter HTTP {exc.code}: {body[:500]}") from exc
    except error.URLError as exc:
        raise OpenRouterError(f"OpenRouter request failed: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"OpenRouter returned invalid JSON: {raw[:500]}") from exc


def extract_message_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise OpenRouterError("OpenRouter returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        joined = "\n".join(part for part in parts if part).strip()
        if joined:
            return joined
    raise OpenRouterError("OpenRouter returned no text content.")
