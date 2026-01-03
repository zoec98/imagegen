"""Utilities for invoking fal endpoints and persisting generated images."""

from __future__ import annotations

import secrets
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping, MutableSequence, Sequence
from email.message import Message
from io import BytesIO
from pathlib import Path
from pprint import pprint
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from . import exif
from .options import ParsedOptions

try:  # pragma: no cover - lazy import fallback
    import fal_client  # type: ignore
except ImportError:  # pragma: no cover
    fal_client = None  # type: ignore


def generate_images(
        parsed: ParsedOptions, *, output_dir: Path | None = None
) -> list[Path]:
    """Invoke the target fal endpoint and download any returned images."""

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
    request_id = _extract_request_id(payload) or getattr(invocation, "request_id", None)
    if not request_id:
        request_id = secrets.token_hex(8)

    urls = _extract_urls(payload)
    if not urls:
        raise ValueError("fal_client response did not include any image URLs")

    if output_dir is None:
        output_dir = Path("assets")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_component = _base_name_from_params(arguments) or parsed.model
    base_component = _sanitize_component(base_component)
    request_component = _sanitize_component(request_id)

    written: list[Path] = []
    for index, url in enumerate(urls, start=1):
        data, content_type = _download(url)
        suffix = _extension_for_url(url, content_type)
        convert_to_jpg = parsed.as_jpg and suffix == ".png"
        if convert_to_jpg:
            suffix = ".jpg"
        filename = f"{base_component}-{index}-{request_component}{suffix}"
        path = output_dir / filename
        if convert_to_jpg:
            _write_jpg(path, data, parsed.jpg_options)
        else:
            path.write_bytes(data)
        _apply_exif_metadata(path, parsed)
        if parsed.preview_assets:
            _handle_post_write(path)
        written.append(path)

    return written


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
    print("Request:")
    pprint(
        {
            "endpoint": endpoint,
            "call": call_type,
            "arguments": arguments,
        }
    )


def _emit_elapsed(elapsed_seconds: float) -> None:
    formatted = _format_elapsed(elapsed_seconds)
    print(f"Elapsed time: {formatted}")


def _format_elapsed(elapsed_seconds: float) -> str:
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


def _handle_post_write(path: Path) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(["/usr/bin/open", str(path)], check=False) # noqa: S603 - intended.
    except OSError:
        pass


def _apply_exif_metadata(path: Path, parsed: ParsedOptions) -> None:
    description: str | None = None
    if parsed.add_prompt_metadata:
        prompt_value = parsed.params.get("prompt")
        if isinstance(prompt_value, str):
            stripped = prompt_value.strip()
            if stripped:
                description = stripped

    model = f"{parsed.model}"
    success = exif.set_exif_data(path, description=description, model=model)
    if not success:
        print(f"warning: unable to update EXIF data for {path}", file=sys.stderr)


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


__all__ = ["generate_images", "upload_image"]
