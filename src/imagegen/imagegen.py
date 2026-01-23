"""Utilities for invoking fal endpoints and persisting generated images."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping, MutableSequence, Sequence
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from image_common.env import save_clean_copy_enabled

from . import exif
from .options import ParsedOptions, get_safetensors_url, get_source_image_url

try:  # pragma: no cover - lazy import fallback
    import fal_client  # type: ignore
except ImportError:  # pragma: no cover
    fal_client = None  # type: ignore

logger = logging.getLogger(__name__)


def _truncate_to_word_boundary(text: str, max_chars: int = 50) -> str:
    """Truncate text to max_chars, rounding down to nearest complete word."""
    if len(text) <= max_chars:
        return text

    # Find the last space within the limit
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")

    if last_space > 0:
        return truncated[:last_space]

    # If no space found, just truncate at max_chars
    return truncated


def generate_images(
    parsed: ParsedOptions, *, output_dir: Path | None = None
) -> list[Path]:
    """Invoke the target fal endpoint and download any returned images."""
    written, _ = generate_images_with_urls(parsed, output_dir=output_dir)
    return written


def generate_images_with_urls(
    parsed: ParsedOptions, *, output_dir: Path | None = None
) -> tuple[list[Path], list[str]]:
    """Invoke the target fal endpoint and return paths with their source URLs."""

    client = _require_fal_client()

    endpoint = parsed.endpoint
    arguments = dict(parsed.params)
    call_type = parsed.call.lower()

    _emit_request_info(endpoint, call_type, arguments)
    start_time = time.perf_counter()

    if call_type == "subscribe":
        invocation = client.subscribe(endpoint, arguments=arguments, with_logs=False)
    else:
        invocation = client.run(endpoint, arguments=arguments)

    elapsed = time.perf_counter() - start_time
    _emit_elapsed(elapsed)

    payload = _coerce_payload(invocation)

    # Generate timestamp for filename (YYYYMMDD_HHMMSS)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    urls = _extract_urls(payload)
    if not urls:
        raise ValueError("fal_client response did not include any image URLs")

    if output_dir is None:
        output_dir = Path("assets")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get prompt name from file parameter (if exists)
    prompt_name = _base_name_from_params(arguments)

    # Get prompt text from parameters
    prompt_text = arguments.get("prompt", "")
    if isinstance(prompt_text, str):
        prompt_text = prompt_text.strip()
    else:
        prompt_text = ""

    # Build base component based on what we have
    if prompt_name:
        # If we have a prompt name, use: prompt_name + truncated_prompt_text
        sanitized_name = _sanitize_component(prompt_name)
        sanitized_text = _sanitize_component(prompt_text)
        truncated_text = _truncate_to_word_boundary(sanitized_text, max_chars=50)
        base_component = (
            f"{sanitized_name}-{truncated_text}" if truncated_text else sanitized_name
        )
    elif prompt_text:
        # If no prompt name but we have prompt text, use truncated prompt text
        sanitized_text = _sanitize_component(prompt_text)
        base_component = _truncate_to_word_boundary(sanitized_text, max_chars=50)
    else:
        # Fallback to model name if we have nothing
        base_component = _sanitize_component(parsed.model)

    written: list[Path] = []
    for _index, url in enumerate(urls, start=1):
        data, content_type = _download(url)
        suffix = _extension_for_url(url, content_type)
        convert_to_jpg = parsed.as_jpg and suffix == ".png"
        if convert_to_jpg:
            suffix = ".jpg"
        filename = f"{base_component}-{timestamp}{suffix}"
        path = output_dir / filename
        if convert_to_jpg:
            _write_jpg(path, data, parsed.jpg_options)
        else:
            path.write_bytes(data)
        _apply_exif_metadata(path, parsed)
        _save_clean_copy(path, output_dir)
        if parsed.preview_assets:
            _handle_post_write(path)
        written.append(path)

    return written, urls


def _coerce_payload(invocation: Any) -> Any:
    payload = invocation
    if isinstance(payload, Mapping):
        return payload

    accessor_methods = ("get", "result", "value", "json")
    for method_name in accessor_methods:
        method = getattr(payload, method_name, None)
        if callable(method) and not isinstance(payload, Mapping):
            try:
                next_payload = method()
            except TypeError:
                continue
            if next_payload is not None:
                payload = next_payload
            if isinstance(payload, Mapping):
                return payload

    return payload


def _extract_request_id(payload: Any) -> str | None:
    for key in ("request_id", "requestId", "id"):
        value = _search_first(payload, key)
        if isinstance(value, str):
            return value
    return None


def _extract_urls(payload: Any) -> list[str]:
    collected: list[str] = []
    seen = set()
    for candidate in _iter_payload(payload):
        if isinstance(candidate, str) and candidate.lower().startswith("http"):
            if candidate not in seen:
                collected.append(candidate)
                seen.add(candidate)
    return collected


def _iter_payload(value: Any) -> Iterable[Any]:
    stack: MutableSequence[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for nested in reversed(list(current.values())):
                stack.append(nested)
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            for item in reversed(list(current)):
                stack.append(item)
        else:
            yield current


def _search_first(value: Any, key: str) -> Any:
    stack: MutableSequence[Any] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for map_key, map_value in current.items():
                if map_key == key:
                    return map_value
                stack.append(map_value)
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            stack.extend(current)
    return None


def _base_name_from_params(parameters: Mapping[str, Any]) -> str | None:
    file_value = parameters.get("file")
    if isinstance(file_value, str):
        return Path(file_value).stem
    return None


def _sanitize_component(component: str) -> str:
    filtered = [(char.lower() if char.isalnum() else "-") for char in component.strip()]
    sanitized = "".join(filtered).strip("-")
    return sanitized or "image"


def _download(url: str) -> tuple[bytes, str | None]:
    _ALLOWED_SCHEMES = {"http", "https"}
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported Scheme: {parsed.scheme} (allowed: {_ALLOWED_SCHEMES})"
        )

    with urllib.request.urlopen(url) as response:  # noqa: S310 - we do check in the block above.
        data = response.read()
        info = response.info()
        content_type: str | None = None
        if isinstance(info, Message):
            content_type = info.get_content_type()
        else:
            content_type = info.get("Content-Type")
    return data, content_type


def _extension_for_url(url: str, content_type: str | None) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix.lower()

    if suffix in {".png", ".jpg", ".jpeg"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    if content_type:
        lowered = content_type.lower()
        if "png" in lowered:
            return ".png"
        if "jpeg" in lowered or "jpg" in lowered:
            return ".jpg"

    return ".png"


def _require_fal_client():
    global fal_client
    if fal_client is None:  # type: ignore[truthy-function]
        try:
            import fal_client as imported  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "fal_client is required to generate images. "
                "Install the fal SDK and ensure it is importable."
            ) from exc
        fal_client = imported  # type: ignore
    return fal_client  # type: ignore


def _emit_request_info(
    endpoint: str, call_type: str, arguments: Mapping[str, Any]
) -> None:
    logger.warning(
        "Request: %s",
        {
            "endpoint": endpoint,
            "call": call_type,
            "arguments": arguments,
        },
    )


def _emit_elapsed(elapsed_seconds: float) -> None:
    formatted = _format_elapsed(elapsed_seconds)
    logger.info("Elapsed time: %s", formatted)


def _format_elapsed(elapsed_seconds: float) -> str:
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


def _handle_post_write(path: Path) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(["/usr/bin/open", str(path)], check=False)  # noqa: S603 - intended.
    except OSError:
        logger.debug("Failed to open preview for %s.", path, exc_info=True)


def build_exif_description(parsed: ParsedOptions) -> str | None:
    if not parsed.add_prompt_metadata:
        return None

    arguments = dict(parsed.params)
    # We don't want to leak local file names
    arguments.pop("file", None)
    # We don't want to leak image server URLs
    source_base = get_source_image_url()
    safetensors_base = get_safetensors_url()

    for key in ("image_url", "image_urls"):
        value = arguments.get(key)
        if isinstance(value, str):
            if value.startswith(source_base):
                arguments[key] = value[len(source_base) :]
        elif isinstance(value, list):
            shortened: list[Any] = []
            for entry in value:
                if isinstance(entry, str) and entry.startswith(source_base):
                    shortened.append(entry[len(source_base) :])
                else:
                    shortened.append(entry)
            arguments[key] = shortened

    # Also don't leak SAFETENSOR URLs
    loras_value = arguments.get("loras")
    if isinstance(loras_value, list):
        normalized_loras: list[Any] = []
        for entry in loras_value:
            if isinstance(entry, dict):
                lora_path = entry.get("path")
                if isinstance(lora_path, str) and lora_path.startswith(
                    safetensors_base
                ):
                    updated = dict(entry)
                    updated["path"] = lora_path[len(safetensors_base) :]
                    normalized_loras.append(updated)
                else:
                    normalized_loras.append(entry)
            elif isinstance(entry, str) and entry.startswith(safetensors_base):
                normalized_loras.append(entry[len(safetensors_base) :])
            else:
                normalized_loras.append(entry)
        arguments["loras"] = normalized_loras

    desc_data = {
        "model": parsed.model,
        "endpoint": parsed.endpoint,
        "call": parsed.call,
        "arguments": arguments,
    }
    if parsed.extra_metadata:
        desc_data.update(parsed.extra_metadata)

    return json.dumps(
        desc_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _apply_exif_metadata(path: Path, parsed: ParsedOptions) -> None:
    description = build_exif_description(parsed)
    model = f"{parsed.model}"
    success = exif.set_exif_data(path, description=description, model=model)
    if not success:
        logger.warning("Unable to update EXIF data for %s.", path)


def _write_jpg(path: Path, data: bytes, options: Mapping[str, Any]) -> None:
    with Image.open(BytesIO(data)) as img:
        has_alpha = img.mode in {"RGBA", "LA"} or (
            img.mode == "P" and "transparency" in img.info
        )
        if has_alpha:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(path, format="JPEG", **dict(options))


def upload_image(path: Path) -> str:
    """Upload a local file to fal storage and return the URL."""
    client = _require_fal_client()
    # verify path exists
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    url = client.upload_file(str(path))
    return url


def _save_clean_copy(source_path: Path, output_dir: Path) -> None:
    """Save a copy of the image to a sibling 'clean' directory with no EXIF."""
    if not save_clean_copy_enabled():
        return
    try:
        if output_dir.name == "":
            # Handle edge case where output_dir might be just a name like 'assets' without full path logic sometimes?
            # Path('assets').name is 'assets'. Path('.').name is ''.
            # If output_dir is '.', name is empty.
            clean_dir_name = "clean_images"
            if output_dir.as_posix() != ".":
                clean_dir_name = f"{output_dir.as_posix()}_clean"
            clean_dir = output_dir.parent / clean_dir_name
        else:
            clean_dir = output_dir.parent / f"{output_dir.name}_clean"

        clean_dir.mkdir(parents=True, exist_ok=True)
        target_path = clean_dir / source_path.name

        with Image.open(source_path) as img:
            # Create a new image to ensure no metadata carries over
            clean_img = Image.frombytes(img.mode, img.size, img.tobytes())
            clean_img.save(target_path)
    except Exception as e:
        # Don't fail the main generation if clean copy fails
        logger.warning("Failed to save clean copy: %s", e)


__all__ = ["generate_images", "upload_image", "save_clean_copy_enabled"]
