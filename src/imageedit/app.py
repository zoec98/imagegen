"""Flask scaffolding for the image editor UI."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask

from image_common.env import load_env_file, save_clean_copy_enabled
from image_common.logging import configure_logging
from imagegen.registry import MODEL_REGISTRY

from .forms import (
    default_option,
    get_allowed_sizes,
    model_supports_image_urls,
    parse_checkbox,
)
from .routes import bp as routes_bp
from .services.assets import prompt_name_from_asset_filename
from .services.prompts import next_copy_name


def create_app(*, config: dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""

    env_path = load_env_file(Path(".env"))
    load_dotenv(env_path)
    configure_logging()
    logger = logging.getLogger(__name__)

    app = Flask(__name__)
    app.config.from_mapping(
        PROMPTS_DIR=Path("prompts"),
        ASSETS_DIR=Path("assets"),
        STYLES_DIR=Path("styles"),
    )
    if config:
        app.config.update(config)

    _set_startup_model(app)
    _init_storage_dirs(app)
    app.register_blueprint(routes_bp)

    _start_prune_thread(app, logger)

    return app


def _set_startup_model(app: Flask) -> None:
    startup_model = app.config.get("STARTUP_MODEL") or os.getenv("STARTUP_MODEL", "")
    if startup_model not in MODEL_REGISTRY:
        valid = ", ".join(sorted(MODEL_REGISTRY.keys()))
        raise ValueError(
            f"STARTUP_MODEL must be one of: {valid}. Current value: {startup_model!r}"
        )
    app.config["STARTUP_MODEL"] = startup_model


def _start_prune_thread(app: Flask, logger: logging.Logger) -> None:
    if app.config.get("TESTING"):
        return

    from .services.uploads import prune_upload_history

    def _prune() -> None:
        with app.app_context():
            try:
                prune_upload_history()
            except Exception:
                # Avoid breaking startup if pruning fails.
                logger.warning("Upload history prune failed.", exc_info=True)
                return

    threading.Thread(target=_prune, daemon=True).start()


def _init_storage_dirs(app: Flask) -> None:
    prompts_dir = Path(app.config["PROMPTS_DIR"])
    styles_dir = Path(app.config["STYLES_DIR"])
    assets_dir = Path(app.config["ASSETS_DIR"])

    prompts_dir.mkdir(parents=True, exist_ok=True)
    styles_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    if save_clean_copy_enabled():
        clean_dir = assets_dir.parent / f"{assets_dir.name}_clean"
        clean_dir.mkdir(parents=True, exist_ok=True)


_default_option = default_option
_get_allowed_sizes = get_allowed_sizes
_parse_checkbox = parse_checkbox
_model_supports_image_urls = model_supports_image_urls
_next_copy_name = next_copy_name
_prompt_name_from_asset_filename = prompt_name_from_asset_filename

__all__ = [
    "create_app",
    "_default_option",
    "_get_allowed_sizes",
    "_parse_checkbox",
    "_model_supports_image_urls",
    "_next_copy_name",
    "_prompt_name_from_asset_filename",
]


app = create_app()
