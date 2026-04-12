from __future__ import annotations

import os
from dataclasses import dataclass

from engine.utils import read_env_file


@dataclass(frozen=True)
class OpenRouterConfig:
    enabled: bool
    api_key_present: bool
    api_key: str
    base_url: str
    model: str
    app_name: str
    site_url: str


def get_openrouter_config() -> OpenRouterConfig:
    read_env_file()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip() or "https://openrouter.ai/api/v1"
    app_name = os.environ.get("OPENROUTER_APP_NAME", "HAX-Mind").strip() or "HAX-Mind"
    site_url = os.environ.get("OPENROUTER_SITE_URL", "").strip()
    return OpenRouterConfig(
        enabled=bool(api_key),
        api_key_present=bool(api_key),
        api_key=api_key,
        base_url=base_url,
        model=model,
        app_name=app_name,
        site_url=site_url,
    )
