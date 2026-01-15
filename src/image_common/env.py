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
