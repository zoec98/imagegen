"""Form parsing and model option helpers for imageedit."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from imagegen.registry import MODEL_REGISTRY


def size_option_spec(model: str) -> tuple[str | None, dict[str, Any]]:
    model_info = MODEL_REGISTRY.get(model, {})
    options = model_info.get("options", {})
    image_size_spec = options.get("image_size")
    if image_size_spec and image_size_spec.get("type") in {"i", "whi"}:
        return "image_size", image_size_spec
    for name, spec in options.items():
        if name == "image_size":
            continue
        if spec.get("type") in {"i", "whi"}:
            return name, spec
    return None, {}


def default_size_option(model: str) -> str:
    _, spec = size_option_spec(model)
    default = spec.get("default") if spec else None
    if default is None:
        return ""
    return str(default)


def default_option(model: str, option_name: str) -> str:
    model_info = MODEL_REGISTRY.get(model, {})
    options = model_info.get("options", {})
    option = options.get(option_name, {})
    default = option.get("default")
    if default is None:
        return ""
    return str(default)


def get_allowed_sizes(model: str) -> list[str]:
    _, spec = size_option_spec(model)
    allowed = spec.get("allowed_sizes") if spec else None
    if not allowed:
        return []
    return sorted(str(value) for value in allowed)


def model_supports_image_urls(model: str) -> bool:
    return image_input_mode(model) != "none"


def image_input_mode(model: str) -> str:
    model_info = MODEL_REGISTRY.get(model, {})
    options = model_info.get("options", {})
    if "image_urls" in options:
        return "multi"
    if "image_url" in options:
        return "single"
    return "none"


def parse_checkbox(values: Sequence[str], *, default: bool = False) -> bool:
    if not values:
        return default
    return "on" in values


def parse_gallery_width(raw_value: str | None) -> int:
    try:
        value = int(raw_value) if raw_value is not None else 3
    except ValueError:
        value = 3
    return max(1, min(value, 5))


def parse_gallery_height(raw_value: str | None) -> int:
    try:
        value = int(raw_value) if raw_value is not None else 100
    except ValueError:
        value = 100
    return max(1, value)
