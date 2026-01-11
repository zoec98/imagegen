"""Generation orchestration for imageedit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from image_common.prompts import split_multivalue_field
from imagegen.imagegen import generate_images
from imagegen.options import parse_args


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

    try:
        paths = [str(path) for path in generate_images(parsed)]
    except Exception as exc:  # pragma: no cover - depends on fal_client
        return {"error": str(exc), "paths": [], "message": None}

    message = f"Generated {len(paths)} image(s) with '{selected_model}'."
    return {"error": None, "paths": paths, "message": message}
