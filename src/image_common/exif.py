"""EXIF parsing helpers shared across components."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import piexif  # type: ignore[import-untyped]
from PIL import Image

logger = logging.getLogger(__name__)


def extract_prompt_from_exif(asset_path: Path) -> dict[str, Any]:
    try:
        with Image.open(asset_path) as img:
            exif = img.getexif()
    except Exception:
        logger.debug("Failed to load EXIF data for %s.", asset_path, exc_info=True)
        exif = None

    description = exif.get(piexif.ImageIFD.ImageDescription) if exif else None
    if not description:
        return {}
    if isinstance(description, bytes):
        text = description.decode("utf-8", errors="ignore")
    else:
        text = str(description)
    return parse_exif_description(normalize_exif_text(text))


def parse_exif_description(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    trimmed = text.strip()
    if trimmed.startswith("{"):
        try:
            data = json.loads(trimmed)
            if isinstance(data, dict):
                result["model"] = data.get("model")
                result["style"] = data.get("style_name")
                result["prompt_name"] = data.get("prompt_name")
                arguments = data.get("arguments", {})
                if isinstance(arguments, dict):
                    result["prompt"] = arguments.get("prompt")
                return result
        except json.JSONDecodeError:
            logger.debug("Failed to parse EXIF JSON description.")

    prompt_index = text.find("Prompt:")
    if prompt_index == -1:
        return result

    prompt_text = text[prompt_index + len("Prompt:") :].strip()
    model_text = None
    model_index = text.find("Model:")
    if 0 <= model_index < prompt_index:
        model_text = text[model_index + len("Model:") : prompt_index].strip()

    result["prompt"] = prompt_text
    result["model"] = model_text
    return result


def normalize_exif_text(text: str) -> str:
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text
