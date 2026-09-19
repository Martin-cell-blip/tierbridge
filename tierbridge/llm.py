"""OpenAI-compatible chat client for optional AI drafting (TIERBRIDGE_* env vars)."""
from __future__ import annotations

import json
import os

import requests

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT_S = 120


class LLMNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("TIERBRIDGE_API_KEY"))


def chat(messages: list[dict], temperature: float = 0.4) -> str:
    api_key = os.environ.get("TIERBRIDGE_API_KEY")
    if not api_key:
        raise LLMNotConfigured("Set TIERBRIDGE_API_KEY to enable AI worksheet drafting.")
    base_url = os.environ.get("TIERBRIDGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("TIERBRIDGE_MODEL", DEFAULT_MODEL)
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": temperature,
              "response_format": {"type": "json_object"}},
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model response")
    return json.loads(text[start:end + 1])
