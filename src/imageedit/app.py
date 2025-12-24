"""Flask scaffolding for the upcoming image editor UI."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, send_from_directory

from imagegen.imagegen import generate_images
from imagegen.options import parse_args
from imagegen.registry import MODEL_REGISTRY


def create_app(*, config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""

    app = Flask(__name__)
    app.config.from_mapping(
        PROMPTS_DIR=Path("prompts"),
        ASSETS_DIR=Path("assets"),
        STYLES_DIR=Path("styles"),
    )
    if config:
        app.config.update(config)

    all_models = sorted(MODEL_REGISTRY.keys())

    @app.route("/", methods=["GET", "POST"])
    def index() -> str:
        """Render a prompt CRUD view backed by files under prompts/."""

        prompts_dir = Path(app.config["PROMPTS_DIR"])
        prompts_dir.mkdir(parents=True, exist_ok=True)
        prompt_names = _list_prompt_names(prompts_dir)
        styles_dir = Path(app.config["STYLES_DIR"])
        style_names = _list_prompt_names(styles_dir)

        selected_prompt = request.args.get("prompt", "").strip()
        selected_style = request.form.get("style_name", "").strip()
        prompt_text = ""
        status_message: str | None = None
        error_message: str | None = None
        generated_paths: list[str] = []
        asset_entries: list[dict[str, str]] = []

        selected_model = (
            request.form.get("model_name")
            or request.args.get("model")
            or (all_models[0] if all_models else "")
        )
        image_size_value = request.form.get(
            "image_size", _default_option(selected_model, "image_size")
        )
        include_prompt_metadata = request.form.get("include_prompt_metadata") == "on"
        image_urls_text = request.form.get("image_urls", "")
        supports_image_urls = _model_supports_image_urls(selected_model)
        gallery_width = _parse_gallery_width(
            request.args.get("gallery_width") or request.form.get("gallery_width")
        )
        gallery_height = _parse_gallery_height(
            request.args.get("gallery_height") or request.form.get("gallery_height")
        )

        if request.method == "POST":
            action = request.form.get("action", "")
            raw_name = request.form.get("prompt_name", "")
            selected_prompt = _normalize_prompt_name(raw_name)
            prompt_text = request.form.get("prompt_text", "")

            if action == "append_style":
                prompt_text = _append_style_prompt(
                    prompt_text, styles_dir, selected_style
                )
                if selected_style:
                    status_message = f"Added style '{selected_style}'."
            else:
                if not selected_prompt:
                    error_message = "Prompt name is required."
                else:
                    prompt_path = _prompt_path(prompts_dir, selected_prompt)
                    if action == "save":
                        _write_prompt(prompt_path, prompt_text)
                        status_message = f"Saved prompt '{selected_prompt}'."
                        if selected_prompt not in prompt_names:
                            prompt_names.append(selected_prompt)
                            prompt_names.sort()
                    elif action == "delete":
                        if prompt_path.exists():
                            prompt_path.unlink()
                            status_message = f"Deleted prompt '{selected_prompt}'."
                            prompt_names = _list_prompt_names(prompts_dir)
                            selected_prompt = ""
                            prompt_text = ""
                        else:
                            error_message = (
                                f"Prompt '{selected_prompt}' does not exist."
                            )
                    elif action == "duplicate":
                        if prompt_path.exists():
                            prompt_text = prompt_path.read_text(encoding="utf-8")
                            duplicate_name = _next_copy_name(selected_prompt)
                            duplicate_path = _prompt_path(prompts_dir, duplicate_name)
                            _write_prompt(duplicate_path, prompt_text)
                            selected_prompt = duplicate_name
                            status_message = (
                                f"Duplicated prompt as '{selected_prompt}'."
                            )
                            if selected_prompt not in prompt_names:
                                prompt_names.append(selected_prompt)
                                prompt_names.sort()
                        else:
                            error_message = (
                                f"Prompt '{selected_prompt}' does not exist."
                            )
                    elif action == "load":
                        if prompt_path.exists():
                            prompt_text = prompt_path.read_text(encoding="utf-8")
                            status_message = f"Loaded prompt '{selected_prompt}'."
                        else:
                            prompt_text = ""
                            error_message = f"Prompt '{selected_prompt}' does not exist."
                    elif action == "run":
                        if not selected_model:
                            error_message = "A model must be selected before running."
                        else:
                            _write_prompt(prompt_path, prompt_text)
                            run_result = _run_generation(
                                selected_model=selected_model,
                                prompt_name=selected_prompt,
                                prompt_path=prompt_path,
                                include_prompt_metadata=include_prompt_metadata,
                                image_size=image_size_value,
                                image_urls=image_urls_text if supports_image_urls else "",
                            )
                            if run_result["error"]:
                                error_message = run_result["error"]
                            else:
                                generated_paths = run_result["paths"]
                                asset_entries = _build_asset_entries(
                                    generated_paths, Path(app.config["ASSETS_DIR"])
                                )
                                status_message = run_result["message"]
                    else:
                        error_message = "Unknown action."

        if request.method == "GET" and selected_prompt:
            prompt_path = _prompt_path(prompts_dir, selected_prompt)
            if prompt_path.exists():
                prompt_text = prompt_path.read_text(encoding="utf-8")

        allowed_sizes = _get_allowed_sizes(selected_model)
        assets_dir = Path(app.config["ASSETS_DIR"])
        asset_paths = _list_asset_paths(assets_dir)
        gallery_limit = gallery_width * gallery_height
        gallery_entries = _build_gallery_entries(
            asset_paths[:gallery_limit], assets_dir
        )

        return render_template(
            "index.html",
            prompt_names=prompt_names,
            selected_prompt=selected_prompt,
            style_names=style_names,
            selected_style=selected_style,
            prompt_text=prompt_text,
            status_message=status_message,
            error_message=error_message,
            model_names=all_models,
            selected_model=selected_model,
            image_size_value=image_size_value,
            allowed_sizes=allowed_sizes,
            include_prompt_metadata=include_prompt_metadata,
            supports_image_urls=supports_image_urls,
            image_urls_text=image_urls_text,
            generated_paths=generated_paths,
            asset_route="asset",
            asset_entries=asset_entries,
            asset_count=len(asset_paths),
            gallery_width=gallery_width,
            gallery_height=gallery_height,
            gallery_entries=gallery_entries,
        )

    @app.route("/assets/<path:filename>")
    def asset(filename: str):
        assets_dir = Path(app.config["ASSETS_DIR"])
        if not assets_dir.is_absolute():
            assets_dir = (Path.cwd() / assets_dir).resolve()
        return send_from_directory(str(assets_dir), filename, as_attachment=False)

    return app


def _run_generation(
    *,
    selected_model: str,
    prompt_name: str,
    prompt_path: Path,
    include_prompt_metadata: bool,
    image_size: str,
    image_urls: str,
) -> dict[str, Any]:
    args: list[str] = [selected_model, "--no-preview", "-f", str(prompt_path)]
    if include_prompt_metadata:
        args.append("-a")
    if image_size.strip():
        args.extend(["-i", image_size.strip()])
    for url in _split_multivalue_field(image_urls):
        args.extend(["-u", url])

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


def _list_prompt_names(prompts_dir: Path) -> list[str]:
    names: list[str] = []
    for path in prompts_dir.glob("*.txt"):
        names.append(path.stem)
    return sorted(names)


def _prompt_path(prompts_dir: Path, prompt_name: str) -> Path:
    sanitized = _normalize_prompt_name(prompt_name)
    return prompts_dir / f"{sanitized}.txt"


def _normalize_prompt_name(raw_name: str) -> str:
    candidate = raw_name.strip()
    if not candidate:
        return ""
    candidate = Path(candidate).name
    if candidate.endswith(".txt"):
        candidate = candidate[:-4]
    return candidate


def _write_prompt(path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalized, encoding="utf-8")


def _append_style_prompt(prompt_text: str, styles_dir: Path, style_name: str) -> str:
    sanitized = _normalize_prompt_name(style_name)
    if not sanitized:
        return prompt_text

    style_path = styles_dir / f"{sanitized}.txt"
    if not style_path.exists():
        return prompt_text

    style_text = style_path.read_text(encoding="utf-8")
    if not style_text:
        return prompt_text

    normalized_prompt = prompt_text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized_prompt:
        return f"{normalized_prompt.rstrip()}\n{style_text}"
    return style_text


def _next_copy_name(prompt_name: str) -> str:
    match = re.fullmatch(r"(.+)_copy(\d+)?", prompt_name)
    if match:
        base = match.group(1)
        number = match.group(2)
        if number is None:
            return f"{base}_copy2"
        return f"{base}_copy{int(number) + 1}"
    return f"{prompt_name}_copy"


def _size_option_spec(model: str) -> tuple[str | None, dict[str, Any]]:
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


def _default_size_option(model: str) -> str:
    _, spec = _size_option_spec(model)
    default = spec.get("default") if spec else None
    if default is None:
        return ""
    return str(default)


def _default_option(model: str, option_name: str) -> str:
    model_info = MODEL_REGISTRY.get(model, {})
    options = model_info.get("options", {})
    option = options.get(option_name, {})
    default = option.get("default")
    if default is None:
        return ""
    return str(default)


def _get_allowed_sizes(model: str) -> list[str]:
    _, spec = _size_option_spec(model)
    allowed = spec.get("allowed_sizes") if spec else None
    if not allowed:
        return []
    return sorted(str(value) for value in allowed)


def _build_asset_entries(
    paths: Sequence[str], assets_dir: Path
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw in paths:
        filename = _relative_asset_path(Path(raw), assets_dir)
        entries.append({"display": raw, "filename": filename})
    return entries


def _build_gallery_entries(
    paths: Sequence[Path], assets_dir: Path
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in paths:
        filename = _relative_asset_path(path, assets_dir)
        entries.append({"display": filename, "filename": filename})
    return entries


def _list_asset_paths(assets_dir: Path) -> list[Path]:
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    if not assets_dir.exists():
        return []
    candidates = [path for path in assets_dir.iterdir() if path.is_file()]
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def _relative_asset_path(path: Path, assets_dir: Path) -> str:
    target = path if path.is_absolute() else Path.cwd() / path
    try:
        resolved_target = target.resolve()
    except FileNotFoundError:
        resolved_target = target
    assets_root = assets_dir if assets_dir.is_absolute() else Path.cwd() / assets_dir
    try:
        resolved_assets = assets_root.resolve()
    except FileNotFoundError:
        resolved_assets = assets_root
    try:
        return resolved_target.relative_to(resolved_assets).as_posix()
    except ValueError:
        return resolved_target.name


def _model_supports_image_urls(model: str) -> bool:
    model_info = MODEL_REGISTRY.get(model, {})
    options = model_info.get("options", {})
    return "image_urls" in options


def _split_multivalue_field(raw_value: str) -> list[str]:
    values: list[str] = []
    for chunk in raw_value.splitlines():
        parts = [part.strip() for part in chunk.split(",") if part.strip()]
        values.extend(parts)
    return values


def _parse_gallery_width(raw_value: str | None) -> int:
    try:
        value = int(raw_value) if raw_value is not None else 3
    except ValueError:
        value = 3
    return max(1, min(value, 5))


def _parse_gallery_height(raw_value: str | None) -> int:
    allowed = {value for value in range(5, 105, 5)}
    try:
        value = int(raw_value) if raw_value is not None else 5
    except ValueError:
        value = 5
    if value not in allowed:
        return 5
    return value


app = create_app()
