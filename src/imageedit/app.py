"""Flask scaffolding for the upcoming image editor UI."""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import piexif  # type: ignore[import-untyped]
from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image

from imagegen.imagegen import generate_images, upload_image
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
        selected_style = (
            request.form.get("style_name_custom", "").strip()
            or request.form.get("style_name_preset", "").strip()
            or request.form.get("style_name", "").strip()
        )
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
            "image_size_preset", _default_option(selected_model, "image_size")
        )
        include_prompt_metadata = _parse_checkbox(
            request.form.getlist("include_prompt_metadata"), default=True
        )
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
            raw_name = (
                request.form.get("prompt_name_custom", "").strip()
                or request.form.get("prompt_name_preset", "").strip()
                or request.form.get("prompt_name", "").strip()
            )
            selected_prompt = _normalize_prompt_name(raw_name)
            prompt_text = request.form.get("prompt_text", "")

            if action in {"asset_load", "asset_delete"}:
                assets_dir = Path(app.config["ASSETS_DIR"])
                asset_filename = request.form.get("asset_filename", "").strip()
                asset_path = _resolve_asset_path(assets_dir, asset_filename)
                if not asset_path or not asset_path.exists():
                    error_message = "Asset file not found."
                elif action == "asset_delete":
                    asset_path.unlink()
                    status_message = f"Deleted asset '{asset_filename}'."
                else:
                    exif_data = _extract_prompt_from_exif(asset_path)
                    if not exif_data.get("prompt"):
                        error_message = (
                            "No prompt metadata found in the selected asset."
                        )
                    else:
                        prompt_text = exif_data["prompt"]
                        selected_prompt = _prompt_name_from_asset_filename(
                            asset_filename
                        )

                        if exif_data.get("model") and exif_data["model"] in all_models:
                            selected_model = exif_data["model"]

                        if exif_data.get("style"):
                            selected_style = exif_data["style"]

                        if exif_data.get("prompt_name"):
                            selected_prompt = exif_data["prompt_name"]

                        status_message = f"Loaded prompt from asset '{asset_filename}'."
            elif action == "append_style":
                prompt_text = _append_style_prompt(
                    prompt_text, styles_dir, selected_style
                )
                if selected_style:
                    status_message = f"Added style '{selected_style}'."
            else:
                # No other actions needed - prompts are managed via API endpoints
                if action == "run":
                    if not selected_model:
                        error_message = "A model must be selected before running."
                    else:
                        # Define prompt_path for the run action
                        prompt_path = _prompt_path(prompts_dir, selected_prompt)
                        _write_prompt(prompt_path, prompt_text)
                        run_result = _run_generation(
                            selected_model=selected_model,
                            prompt_name=selected_prompt,
                            prompt_path=prompt_path,
                            include_prompt_metadata=include_prompt_metadata,
                            image_size=image_size_value,
                            image_urls=image_urls_text if supports_image_urls else "",
                            style_name=selected_style,
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
        return send_from_directory(str(assets_dir), filename)

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        """Handle local image upload to fal cloud."""

        if "file" not in request.files:
            return {"error": "No file provided"}, 400

        file = request.files["file"]
        if file.filename == "":
            return {"error": "No file selected"}, 400

        try:
            # Save to temp file and upload
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(file.filename).suffix
            ) as temp:
                temp_path = Path(temp.name)
                file.save(temp_path)
                try:
                    url = upload_image(temp_path)
                finally:
                    temp_path.unlink()  # Clean up temp file

            return {"url": url}
        except Exception as e:
            return {"error": str(e)}, 500

    @app.route("/api/model-sizes/<model>")
    def api_model_sizes(model: str):
        """Return allowed sizes for a given model as JSON."""
        sizes = _get_allowed_sizes(model)
        default = _default_option(model, "image_size")
        supports_urls = _model_supports_image_urls(model)
        return jsonify(
            {"sizes": sizes, "default": default, "supports_image_urls": supports_urls}
        )

    @app.route("/api/prompt/<name>")
    def api_get_prompt(name: str):
        """Return prompt text for a given prompt name."""
        prompts_dir = Path(app.config["PROMPTS_DIR"])
        prompt_path = _prompt_path(prompts_dir, name)
        if prompt_path.exists():
            text = prompt_path.read_text(encoding="utf-8")
            return jsonify({"text": text})
        return jsonify({"text": ""}), 404

    @app.route("/api/style/<name>")
    def api_get_style(name: str):
        """Return style text for a given style name."""
        styles_dir = Path(app.config["STYLES_DIR"])
        style_path = _prompt_path(styles_dir, name)  # Reuse _prompt_path logic
        if style_path.exists():
            text = style_path.read_text(encoding="utf-8")
            return jsonify({"text": text})
        return jsonify({"text": ""}), 404

    @app.route("/api/save-style", methods=["POST"])
    def api_save_style():
        """Save a new style, handling naming collisions."""
        data = request.json
        if not data or "name" not in data or "text" not in data:
            return jsonify({"error": "Missing name or text"}), 400

        name = data["name"].strip()
        text = data["text"]
        if not name:
            return jsonify({"error": "Style name cannot be empty"}), 400

        styles_dir = Path(app.config["STYLES_DIR"])
        styles_dir.mkdir(parents=True, exist_ok=True)

        # Determine unique name
        sanitized = _normalize_prompt_name(name)
        base_name = sanitized
        counter = 0
        while True:
            candidate_name = base_name if counter == 0 else f"{base_name}_{counter}"
            style_path = styles_dir / f"{candidate_name}.txt"
            if not style_path.exists():
                break
            counter += 1

        try:
            _write_prompt(style_path, text)
            return jsonify({"success": True, "saved_name": candidate_name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/delete-style", methods=["POST"])
    def api_delete_style():
        """Delete an existing style."""
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Missing name"}), 400

        name = data["name"].strip()
        if not name:
            return jsonify({"error": "Style name cannot be empty"}), 400

        styles_dir = Path(app.config["STYLES_DIR"])
        style_path = _prompt_path(styles_dir, name)

        if not style_path.exists():
            return jsonify({"error": f"Style '{name}' not found"}), 404

        try:
            style_path.unlink()
            return jsonify({"success": True, "deleted_name": name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/save-prompt", methods=["POST"])
    def api_save_prompt():
        """Save a prompt text with a given name."""
        data = request.json
        if not data or "name" not in data or "text" not in data:
            return jsonify({"error": "Missing name or text"}), 400

        name = data["name"].strip()
        text = data["text"]
        if not name:
            return jsonify({"error": "Prompt name cannot be empty"}), 400

        prompts_dir = Path(app.config["PROMPTS_DIR"])
        prompts_dir.mkdir(parents=True, exist_ok=True)

        sanitized = _normalize_prompt_name(name)
        prompt_path = prompts_dir / f"{sanitized}.txt"

        try:
            _write_prompt(prompt_path, text)
            return jsonify({"success": True, "saved_name": sanitized})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/delete-prompt", methods=["POST"])
    def api_delete_prompt():
        """Delete an existing prompt."""
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Missing name"}), 400

        name = data["name"].strip()
        if not name:
            return jsonify({"error": "Prompt name cannot be empty"}), 400

        prompts_dir = Path(app.config["PROMPTS_DIR"])
        prompt_path = _prompt_path(prompts_dir, name)

        if not prompt_path.exists():
            return jsonify({"error": f"Prompt '{name}' not found"}), 404

        try:
            prompt_path.unlink()
            return jsonify({"success": True, "deleted_name": name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/duplicate-prompt", methods=["POST"])
    def api_duplicate_prompt():
        """Duplicate an existing prompt with an incremented name."""
        data = request.json
        if not data or "name" not in data or "text" not in data:
            return jsonify({"error": "Missing name or text"}), 400

        name = data["name"].strip()
        text = data["text"]
        if not name:
            return jsonify({"error": "Prompt name cannot be empty"}), 400

        prompts_dir = Path(app.config["PROMPTS_DIR"])
        prompts_dir.mkdir(parents=True, exist_ok=True)

        # Generate new name using existing logic
        duplicate_name = _next_copy_name(name)
        duplicate_path = _prompt_path(prompts_dir, duplicate_name)

        try:
            _write_prompt(duplicate_path, text)
            return jsonify({"success": True, "duplicated_name": duplicate_name})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def _run_generation(
    *,
    selected_model: str,
    prompt_name: str,
    prompt_path: Path,
    include_prompt_metadata: bool,
    image_size: str,
    image_urls: str,
    style_name: str | None = None,
) -> dict[str, Any]:
    args: list[str] = [selected_model, "--no-preview", "-f", str(prompt_path)]
    if include_prompt_metadata:
        args.append("-a")
    if image_size.strip():
        args.extend(["-i", image_size.strip()])
    for url in _split_multivalue_field(image_urls):
        args.extend(["-u", url])

    # Add extra metadata for EXIF
    meta = {
        "prompt_name": prompt_name,
        "style_name": style_name,
    }
    # Filter out empty values
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
    normalized_style = style_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_prompt = prompt_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized_prompt.splitlines()
    for index, line in enumerate(lines):
        if line.lower().startswith("style:"):
            lines = lines[:index]
            break

    base = "\n".join(lines).rstrip()
    style_line = f"Style: {sanitized}"
    if base and normalized_style:
        return f"{base}\n{style_line}\n{normalized_style}"
    if base:
        return f"{base}\n{style_line}"
    if normalized_style:
        return f"{style_line}\n{normalized_style}"
    return style_line


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


def _resolve_asset_path(assets_dir: Path, filename: str) -> Path | None:
    if not filename:
        return None
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    candidate = (assets_dir / filename).resolve()
    try:
        candidate.relative_to(assets_dir)
    except ValueError:
        return None
    return candidate


def _prompt_name_from_asset_filename(filename: str) -> str:
    name = Path(filename).stem
    match = re.search(r"-\d+", name)
    if match:
        name = name[: match.start()]
    return _normalize_prompt_name(name)


def _extract_prompt_from_exif(asset_path: Path) -> dict[str, Any]:
    try:
        with Image.open(asset_path) as img:
            exif = img.getexif()
    except Exception:
        exif = None

    description = exif.get(piexif.ImageIFD.ImageDescription) if exif else None
    if not description:
        return {}
    if isinstance(description, bytes):
        text = description.decode("utf-8", errors="ignore")
    else:
        text = str(description)
    return _parse_exif_description(_normalize_exif_text(text))


def _parse_exif_description(text: str) -> dict[str, Any]:
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
            pass

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


def _normalize_exif_text(text: str) -> str:
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def _list_asset_paths(assets_dir: Path) -> list[Path]:
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    if not assets_dir.exists():
        return []
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
    candidates = [
        path
        for path in assets_dir.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in allowed_suffixes
    ]
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


def _parse_checkbox(values: Sequence[str], *, default: bool = False) -> bool:
    if not values:
        return default
    return "on" in values


def _parse_gallery_width(raw_value: str | None) -> int:
    try:
        value = int(raw_value) if raw_value is not None else 3
    except ValueError:
        value = 3
    return max(1, min(value, 5))


def _parse_gallery_height(raw_value: str | None) -> int:
    try:
        value = int(raw_value) if raw_value is not None else 100
    except ValueError:
        value = 100
    return max(1, value)


app = create_app()
