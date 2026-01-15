"""Flask routes for imageedit."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from image_common.exif import extract_prompt_from_exif
from image_common.prompts import (
    list_prompt_names,
    normalize_prompt_name,
    prompt_path,
    read_prompt,
    write_prompt,
)
from imagegen.imagegen import save_clean_copy_enabled
from imagegen.registry import MODEL_REGISTRY

from .forms import (
    default_option,
    get_allowed_sizes,
    image_input_mode,
    model_supports_image_urls,
    parse_checkbox,
    parse_gallery_height,
    parse_gallery_width,
)
from .services.assets import (
    build_asset_entries,
    build_gallery_entries,
    list_asset_paths,
    prompt_name_from_asset_filename,
    resolve_asset_path,
)
from .services.generation import run_generation
from .services.prompts import append_style_prompt, next_copy_name
from .services.uploads import upload_local_image

bp = Blueprint("imageedit", __name__)
ALL_MODELS = sorted(MODEL_REGISTRY.keys())


@bp.route("/", methods=["GET", "POST"])
def index() -> str:
    """Render a prompt CRUD view backed by files under prompts/."""

    prompts_dir = Path(current_app.config["PROMPTS_DIR"])
    prompt_names = list_prompt_names(prompts_dir)
    styles_dir = Path(current_app.config["STYLES_DIR"])
    style_names = list_prompt_names(styles_dir)

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
        or current_app.config["STARTUP_MODEL"]
    )
    image_size_value = request.form.get(
        "image_size_preset", default_option(selected_model, "image_size")
    )
    include_prompt_metadata = parse_checkbox(
        request.form.getlist("include_prompt_metadata"), default=True
    )
    image_urls_text = request.form.get("image_urls", "")
    input_mode = image_input_mode(selected_model)
    supports_image_urls = input_mode != "none"
    gallery_width = parse_gallery_width(
        request.args.get("gallery_width") or request.form.get("gallery_width")
    )
    gallery_height = parse_gallery_height(
        request.args.get("gallery_height") or request.form.get("gallery_height")
    )

    if request.method == "POST":
        action = request.form.get("action", "")
        raw_name = (
            request.form.get("prompt_name_custom", "").strip()
            or request.form.get("prompt_name_preset", "").strip()
            or request.form.get("prompt_name", "").strip()
        )
        selected_prompt = normalize_prompt_name(raw_name)
        prompt_text = request.form.get("prompt_text", "")

        if action in {"asset_load", "asset_delete"}:
            assets_dir = Path(current_app.config["ASSETS_DIR"])
            asset_filename = request.form.get("asset_filename", "").strip()
            asset_path = resolve_asset_path(assets_dir, asset_filename)
            if not asset_path or not asset_path.exists():
                error_message = "Asset file not found."
            elif action == "asset_delete":
                asset_path.unlink()

                if save_clean_copy_enabled():
                    try:
                        clean_dir = assets_dir.parent / f"{assets_dir.name}_clean"
                        clean_path = clean_dir / asset_path.name
                        if clean_path.exists():
                            clean_path.unlink()
                    except Exception as e:
                        print(f"Warning: failed to delete clean asset: {e}")

                status_message = f"Deleted asset '{asset_filename}'."
            else:
                exif_data = extract_prompt_from_exif(asset_path)
                if not exif_data.get("prompt"):
                    error_message = "No prompt metadata found in the selected asset."
                else:
                    prompt_text = exif_data["prompt"]
                    selected_prompt = prompt_name_from_asset_filename(asset_filename)

                    if exif_data.get("model") and exif_data["model"] in ALL_MODELS:
                        selected_model = exif_data["model"]

                    if exif_data.get("style"):
                        selected_style = exif_data["style"]

                    if exif_data.get("prompt_name"):
                        selected_prompt = exif_data["prompt_name"]

                    status_message = f"Loaded prompt from asset '{asset_filename}'."
        elif action == "append_style":
            prompt_text = append_style_prompt(prompt_text, styles_dir, selected_style)
            if selected_style:
                status_message = f"Added style '{selected_style}'."
        else:
            if action == "run":
                if not selected_model:
                    error_message = "A model must be selected before running."
                else:
                    prompt_file = prompt_path(prompts_dir, selected_prompt)
                    write_prompt(prompt_file, prompt_text)
                    run_result = run_generation(
                        selected_model=selected_model,
                        prompt_name=selected_prompt,
                        prompt_path=prompt_file,
                        include_prompt_metadata=include_prompt_metadata,
                        image_size=image_size_value,
                        image_urls=image_urls_text if supports_image_urls else "",
                        image_input_mode=input_mode,
                        style_name=selected_style,
                    )
                    if run_result["error"]:
                        error_message = run_result["error"]
                    else:
                        generated_paths = run_result["paths"]
                        asset_entries = build_asset_entries(
                            generated_paths, Path(current_app.config["ASSETS_DIR"])
                        )
                        status_message = run_result["message"]
            elif action:
                error_message = f"Unknown action: {action}"

    if request.method == "GET" and selected_prompt:
        prompt_file = prompt_path(prompts_dir, selected_prompt)
        if prompt_file.exists():
            prompt_text = read_prompt(prompt_file)

    allowed_sizes = get_allowed_sizes(selected_model)
    assets_dir = Path(current_app.config["ASSETS_DIR"])
    asset_paths = list_asset_paths(assets_dir)
    gallery_limit = gallery_width * gallery_height
    gallery_entries = build_gallery_entries(asset_paths[:gallery_limit], assets_dir)

    return render_template(
        "index.html",
        prompt_names=prompt_names,
        selected_prompt=selected_prompt,
        style_names=style_names,
        selected_style=selected_style,
        prompt_text=prompt_text,
        status_message=status_message,
        error_message=error_message,
        model_names=ALL_MODELS,
        selected_model=selected_model,
        image_size_value=image_size_value,
        allowed_sizes=allowed_sizes,
        include_prompt_metadata=include_prompt_metadata,
        supports_image_urls=supports_image_urls,
        image_input_mode=input_mode,
        image_urls_text=image_urls_text,
        generated_paths=generated_paths,
        asset_route="imageedit.asset",
        asset_entries=asset_entries,
        asset_count=len(asset_paths),
        gallery_width=gallery_width,
        gallery_height=gallery_height,
        gallery_entries=gallery_entries,
    )


@bp.route("/assets/<path:filename>")
def asset(filename: str):
    assets_dir = Path(current_app.config["ASSETS_DIR"])
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    return send_from_directory(str(assets_dir), filename)


@bp.route("/api/upload", methods=["POST"])
def api_upload():
    """Handle local image upload to fal cloud."""

    if "file" not in request.files:
        return {"error": "No file provided"}, 400

    file = request.files["file"]
    filename = file.filename or "unknown"
    try:
        url = upload_local_image(file)
        # Verify if we should save history here or if upload_local_image handles it.
        # Ideally, we call the save helper here.
        from .services.uploads import save_upload_to_history

        save_upload_to_history(url, filename)

    except ValueError as exc:
        return {"error": str(exc)}, 400
    except Exception as exc:
        return {"error": str(exc)}, 500

    return {"url": url}


@bp.route("/api/upload-history")
def api_get_upload_history():
    """Return the list of past uploads."""
    from .services.uploads import get_upload_history

    return jsonify(get_upload_history())


@bp.route("/api/model-sizes/<model>")
def api_model_sizes(model: str):
    """Return allowed sizes for a given model as JSON."""
    sizes = get_allowed_sizes(model)
    default = default_option(model, "image_size")
    supports_urls = model_supports_image_urls(model)
    return jsonify(
        {"sizes": sizes, "default": default, "supports_image_urls": supports_urls}
    )


@bp.route("/api/prompt/<name>")
def api_get_prompt(name: str):
    """Return prompt text for a given prompt name."""
    prompts_dir = Path(current_app.config["PROMPTS_DIR"])
    prompt_file = prompt_path(prompts_dir, name)
    if prompt_file.exists():
        text = read_prompt(prompt_file)
        return jsonify({"text": text})
    return jsonify({"text": ""}), 404


@bp.route("/api/style/<name>")
def api_get_style(name: str):
    """Return style text for a given style name."""
    styles_dir = Path(current_app.config["STYLES_DIR"])
    style_path = prompt_path(styles_dir, name)
    if style_path.exists():
        text = read_prompt(style_path)
        return jsonify({"text": text})
    return jsonify({"text": ""}), 404


@bp.route("/api/save-style", methods=["POST"])
def api_save_style():
    """Save a new style, handling naming collisions."""
    data = request.json
    if not data or "name" not in data or "text" not in data:
        return jsonify({"error": "Missing name or text"}), 400

    name = data["name"].strip()
    text = data["text"]
    if not name:
        return jsonify({"error": "Style name cannot be empty"}), 400

    styles_dir = Path(current_app.config["STYLES_DIR"])
    styles_dir.mkdir(parents=True, exist_ok=True)

    sanitized = normalize_prompt_name(name)
    base_name = sanitized
    counter = 0
    while True:
        candidate_name = base_name if counter == 0 else f"{base_name}_{counter}"
        style_path = styles_dir / f"{candidate_name}.txt"
        if not style_path.exists():
            break
        counter += 1

    try:
        write_prompt(style_path, text)
        return jsonify({"success": True, "saved_name": candidate_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/delete-style", methods=["POST"])
def api_delete_style():
    """Delete an existing style."""
    data = request.json
    if not data or "name" not in data:
        return jsonify({"error": "Missing name"}), 400

    name = data["name"].strip()
    if not name:
        return jsonify({"error": "Style name cannot be empty"}), 400

    styles_dir = Path(current_app.config["STYLES_DIR"])
    style_path = prompt_path(styles_dir, name)

    if not style_path.exists():
        return jsonify({"error": f"Style '{name}' not found"}), 404

    try:
        style_path.unlink()
        return jsonify({"success": True, "deleted_name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/save-prompt", methods=["POST"])
def api_save_prompt():
    """Save a prompt text with a given name."""
    data = request.json
    if not data or "name" not in data or "text" not in data:
        return jsonify({"error": "Missing name or text"}), 400

    name = data["name"].strip()
    text = data["text"]
    if not name:
        return jsonify({"error": "Prompt name cannot be empty"}), 400

    prompts_dir = Path(current_app.config["PROMPTS_DIR"])
    prompts_dir.mkdir(parents=True, exist_ok=True)

    sanitized = normalize_prompt_name(name)
    prompt_file = prompt_path(prompts_dir, sanitized)

    try:
        write_prompt(prompt_file, text)
        return jsonify({"success": True, "saved_name": sanitized})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/delete-prompt", methods=["POST"])
def api_delete_prompt():
    """Delete an existing prompt."""
    data = request.json
    if not data or "name" not in data:
        return jsonify({"error": "Missing name"}), 400

    name = data["name"].strip()
    if not name:
        return jsonify({"error": "Prompt name cannot be empty"}), 400

    prompts_dir = Path(current_app.config["PROMPTS_DIR"])
    prompt_file = prompt_path(prompts_dir, name)

    if not prompt_file.exists():
        return jsonify({"error": f"Prompt '{name}' not found"}), 404

    try:
        prompt_file.unlink()
        return jsonify({"success": True, "deleted_name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/duplicate-prompt", methods=["POST"])
def api_duplicate_prompt():
    """Duplicate an existing prompt with an incremented name."""
    data = request.json
    if not data or "name" not in data or "text" not in data:
        return jsonify({"error": "Missing name or text"}), 400

    name = data["name"].strip()
    text = data["text"]
    if not name:
        return jsonify({"error": "Prompt name cannot be empty"}), 400

    prompts_dir = Path(current_app.config["PROMPTS_DIR"])
    prompts_dir.mkdir(parents=True, exist_ok=True)

    duplicate_name = next_copy_name(name)
    duplicate_path = prompt_path(prompts_dir, duplicate_name)

    try:
        write_prompt(duplicate_path, text)
        return jsonify({"success": True, "duplicated_name": duplicate_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
