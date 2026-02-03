"""Environment helpers shared across components."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CONFIG_REGISTRY: list[dict[str, Any]] = [
    {
        "key": "FAL_KEY",
        "default_value": '"<add fal.ai api key here>"',
        "help_text": "Generate a fal.ai API key and put it here.",
    },
    {
        "key": "SAFETENSORS_URL",
        "default_value": '"https://example.com/safetensors_for_lora"',
        "help_text": (
            "If you have your own local web server for .safetensor files for lora, "
            "profile the base URL here."
        ),
    },
    {
        "key": "SOURCE_IMAGE_URL",
        "default_value": '"https://example.com/images_for_edit"',
        "help_text": (
            "Optional base URL for source images if using a local web server."
        ),
    },
    {
        "key": "MAX_CONTENT_LENGTH",
        "default_value": "104857600",
        "help_text": "imageedit uses this as the max allowed file upload length (100 MB).",
    },
    {
        "key": "STARTUP_MODEL",
        "default_value": "seedream",
        "help_text": "imageedit startup model (must match a registry key).",
    },
    {
        "key": "API_AUTH_ENABLED",
        "default_value": "false",
        "help_text": "Enable API token auth for imageedit (/api/* routes).",
    },
    {
        "key": "API_TOKEN_SECRET",
        "default_value": '"<set api token secret>"',
        "help_text": "Secret used to sign and verify imageedit API tokens.",
    },
    {
        "key": "API_TOKEN_ISSUER_KEY",
        "default_value": '"<set api token issuer key>"',
        "help_text": "Shared secret required to mint imageedit API tokens.",
    },
    {
        "key": "API_TOKEN_TTL_SECONDS",
        "default_value": "86400",
        "help_text": "Lifetime for issued imageedit API tokens.",
    },
    {
        "key": "API_BROWSER_TOKEN",
        "default_value": '""',
        "help_text": "Optional pre-issued token for the browser UI.",
    },
    {
        "key": "SAVE_CLEAN_COPY",
        "default_value": "on",
        "help_text": (
            "Create a second copy of the image in assets_cleans sans exif data."
        ),
    },
    {
        "key": "LOG_LEVEL",
        "default_value": "INFO",
        "help_text": "Logging level for stdout logging.",
    },
    {
        "key": "LOG_FORMAT",
        "default_value": '"%(asctime)s %(levelname)s %(name)s:%(filename)s:%(lineno)d: %(message)s"',
        "help_text": "Logging format for stdout logging.",
    },
]


def ensure_env_file(env_path: Path | None = None) -> None:
    target = env_path or Path(".env")
    existing_keys: set[str] = set()
    content = ""
    if target.exists():
        content = target.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key:
                existing_keys.add(key)

    missing = [entry for entry in CONFIG_REGISTRY if entry["key"] not in existing_keys]
    if not missing:
        return

    lines: list[str] = []
    if not content:
        lines.append("# Edit this file to match and install as .env in this directory")
        lines.append("")
    else:
        if not content.endswith("\n"):
            lines.append("")
        lines.append("")
        lines.append("# Added by imagegen to ensure required settings exist.")

    for entry in missing:
        help_text = str(entry["help_text"])
        for help_line in help_text.splitlines():
            lines.append(f"# {help_line}")
        lines.append(f"{entry['key']}={entry['default_value']}")
        lines.append("")

    if target.exists():
        target.write_text(content + "\n".join(lines), encoding="utf-8")
    else:
        target.write_text("\n".join(lines), encoding="utf-8")


def load_env_file(env_path: Path | None = None) -> Path:
    target = env_path or Path(".env")
    ensure_env_file(target)
    return target


def read_env_values(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def set_env_values(env_path: Path, updates: dict[str, str]) -> None:
    if not updates:
        return
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = existing.splitlines(keepends=True)
    seen: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")


def strip_env_quotes(value: str) -> str:
    cleaned = value.strip()
    if (
        (cleaned.startswith('"') and cleaned.endswith('"'))
        or (cleaned.startswith("'") and cleaned.endswith("'"))
    ):
        return cleaned[1:-1]
    return cleaned


def is_placeholder_value(value: str) -> bool:
    normalized = strip_env_quotes(value).strip()
    if not normalized:
        return True
    return normalized.startswith("<") and normalized.endswith(">")


def save_clean_copy_enabled() -> bool:
    value = os.getenv("SAVE_CLEAN_COPY", "")
    if not value.strip():
        return False
    return as_boolean(value, key="SAVE_CLEAN_COPY")


def as_boolean(value: str, *, key: str | None = None) -> bool:
    if not key:
        key = "key"
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"value {value} for {key} must be one of 1, 0, true, false, yes, no, on, off"
    )
