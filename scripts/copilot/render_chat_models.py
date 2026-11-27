#!/usr/bin/env python3
"""Generate chatLanguageModels.json using models exposed by Unsloth Studio."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent.parent
VIRTUAL_KEY_VAR = "AGENTGATEWAY_VIRTUAL_KEY"
UNSLOTH_KEY_VAR = "UNSLOTH_API_KEY"
NON_CHAT_TASKS = {"text-to-image", "image-generation", "embeddings", "text-to-speech", "speech-to-text"}


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def fetch_unsloth_models(base_url: str, api_key: str) -> list[dict]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{base_url.rstrip('/')}/models", headers=headers)

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise ValueError(f"Unsloth returned HTTP {error.code} for {request.full_url}") from error
    except URLError as error:
        raise ValueError(f"Cannot reach Unsloth at {request.full_url}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise ValueError("Unsloth returned invalid JSON from its models endpoint") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unsloth models response must contain a 'data' list")

    models = []
    seen = set()
    for record in payload["data"]:
        if not isinstance(record, dict):
            continue
        model_id = record.get("id")
        if not isinstance(model_id, str) or not model_id or model_id in seen:
            continue
        seen.add(model_id)
        task = str(record.get("task", "")).lower()
        if task in NON_CHAT_TASKS:
            continue

        name = record.get("display_name") or model_id
        quant = record.get("quant")
        if quant and quant not in name:
            name = f"{name} ({quant})"
        model = {
            "id": model_id,
            "name": name,
            "url": "http://localhost:4000/v1/chat/completions",
            "toolCalling": True,
        }
        context_length = record.get("context_length") or record.get("max_context_length")
        if isinstance(context_length, int) and context_length > 0:
            model["maxInputTokens"] = context_length
        models.append(model)

    if not models:
        raise ValueError("Unsloth returned no chat models; leaving the existing output unchanged")
    return models


def fetch_copilot_models(base_url: str, api_key: str) -> tuple[list[dict], list[dict]]:
    headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
    request = Request(f"{base_url.rstrip('/')}/models", headers=headers)

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise ValueError(f"Agentgateway returned HTTP {error.code} for {request.full_url}") from error
    except URLError as error:
        raise ValueError(f"Cannot reach Agentgateway at {request.full_url}: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise ValueError("Agentgateway returned invalid JSON from its models endpoint") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Agentgateway models response must contain a 'data' list")

    completions = []
    responses = []
    seen = set()
    for record in payload["data"]:
        if not isinstance(record, dict):
            continue
        model_id = record.get("id")
        if not isinstance(model_id, str) or not model_id.startswith("copilot/") or model_id in seen:
            continue
        seen.add(model_id)

        model_name = model_id.removeprefix("copilot/")
        name = " ".join(part.upper() if part.isdigit() else part.capitalize() for part in model_name.split("-"))
        api_type = "responses" if model_name.startswith("gpt-") else "chat-completions"
        url_suffix = "responses" if api_type == "responses" else "chat/completions"
        model = {
            "id": model_id,
            "name": name,
            "url": f"http://localhost:4000/v1/{url_suffix}",
            "toolCalling": True,
        }
        (responses if api_type == "responses" else completions).append(model)

    if not completions and not responses:
        raise ValueError("Agentgateway returned no Copilot models; leaving the existing output unchanged")
    return completions, responses


def build_configuration(
    virtual_key: str,
    copilot_completions: list[dict],
    copilot_responses: list[dict],
    unsloth_models: list[dict],
) -> list[dict]:
    return [
        {
            "name": "Gateway - Copilot (Completions)",
            "vendor": "customendpoint",
            "apiKey": virtual_key,
            "apiType": "chat-completions",
            "models": copilot_completions,
        },
        {
            "name": "Gateway - Copilot (Responses)",
            "vendor": "customendpoint",
            "apiKey": virtual_key,
            "apiType": "responses",
            "models": copilot_responses,
        },
        {
            "name": "Gateway - Local Unsloth (Completions)",
            "vendor": "customendpoint",
            "apiKey": virtual_key,
            "apiType": "chat-completions",
            "models": unsloth_models,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unsloth-url", default=os.environ.get("UNSLOTH_API_URL", "http://localhost:8000/v1"))
    parser.add_argument("--gateway-url", default=os.environ.get("AGENTGATEWAY_API_URL", "http://localhost:4000/v1"))
    parser.add_argument("--output", type=Path, default=ROOT / "chatLanguageModels.json")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()

    env = read_env_file(args.env_file)
    virtual_key = os.environ.get(VIRTUAL_KEY_VAR) or env.get(VIRTUAL_KEY_VAR, "")
    if not virtual_key:
        print(f"{VIRTUAL_KEY_VAR} is not set in {args.env_file} or in the environment", file=sys.stderr)
        return 1

    unsloth_key = os.environ.get(UNSLOTH_KEY_VAR) or env.get(UNSLOTH_KEY_VAR, "")
    try:
        copilot_completions, copilot_responses = fetch_copilot_models(args.gateway_url, virtual_key)
        unsloth_models = fetch_unsloth_models(args.unsloth_url, unsloth_key)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    rendered = build_configuration(virtual_key, copilot_completions, copilot_responses, unsloth_models)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)

    copilot_count = len(copilot_completions) + len(copilot_responses)
    print(f"wrote {args.output} ({copilot_count} Copilot, {len(unsloth_models)} Unsloth chat models discovered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())