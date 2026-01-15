"""Generation orchestration for imageedit."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from image_common.prompts import split_multivalue_field
from imagegen.imagegen import build_exif_description, generate_images_with_urls
from imagegen.options import parse_args

from .uploads import log_generated_images, log_generation_request, resolve_upload_ids


def run_generation(
    *,
    selected_model: str,
    prompt_name: str,
    prompt_path: Path,
    include_prompt_metadata: bool,
    image_size: str,
    image_urls: str,
    image_input_mode: str,
    style_name: str | None = None,
) -> dict[str, Any]:
    args: list[str] = [selected_model, "--no-preview", "-f", str(prompt_path)]
    if include_prompt_metadata:
        args.append("-a")
    if image_size.strip():
        args.extend(["-i", image_size.strip()])
    urls = split_multivalue_field(image_urls)
    if image_input_mode == "single":
        if len(urls) > 1:
            return {
                "error": "This model only supports a single source image URL.",
                "paths": [],
                "message": None,
            }
        if urls:
            args.extend(["-u", urls[0]])
    else:
        for url in urls:
            args.extend(["-u", url])

    meta = {
        "prompt_name": prompt_name,
        "style_name": style_name,
    }
    meta = {k: v for k, v in meta.items() if v}
    if meta:
        args.extend(["--meta", json.dumps(meta)])

    try:
        parsed = parse_args(args)
    except Exception as exc:
        return {
            "error": f"Unable to parse arguments: {exc}",
            "paths": [],
            "message": None,
        }

    generation_started_at = time.time()
    try:
        paths, download_urls = generate_images_with_urls(parsed)
    except Exception as exc:  # pragma: no cover - depends on fal_client
        return {"error": str(exc), "paths": [], "message": None}
    generation_completed_at = time.time()

    prompt_value = parsed.params.get("prompt", "")
    prompt_text = prompt_value.strip() if isinstance(prompt_value, str) else ""
    seed_value = parsed.params.get("seed")
    image_size_value = parsed.params.get("image_size")
    if image_size_value is None:
        image_size_value = parsed.params.get("aspect_ratio")

    upload_ids = resolve_upload_ids(urls)
    request_id = log_generation_request(
        prompt=prompt_text,
        endpoint=parsed.endpoint,
        model=parsed.model,
        seed=seed_value if isinstance(seed_value, int) else None,
        image_size=image_size_value if isinstance(image_size_value, str) else None,
        prompt_json=build_exif_description(parsed),
        upload_ids=upload_ids,
        generation_started_at=generation_started_at,
        generation_completed_at=generation_completed_at,
    )

    log_generated_images(
        request_id=request_id,
        images=[
            (path.name, url) for path, url in zip(paths, download_urls, strict=False)
        ],
    )

    path_strings = [str(path) for path in paths]
    message = f"Generated {len(path_strings)} image(s) with '{selected_model}'."
    return {"error": None, "paths": path_strings, "message": message}
