"""Flask scaffolding for the image editor UI."""

from __future__ import annotations

import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv
from flask import Flask

from image_common.env import (
    is_placeholder_value,
    load_env_file,
    read_env_values,
    save_clean_copy_enabled,
    set_env_values,
    strip_env_quotes,
)
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
from .services.auth import issue_api_token
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

    _set_configs(app)
    _init_storage_dirs(app)
    app.register_blueprint(routes_bp)
    _register_cli(app)

    _start_prune_thread(app, logger)

    return app


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-env")
    def init_env() -> None:
        """Ensure .env exists and seed imageedit API auth secrets."""
        env_path = load_env_file(Path(".env"))
        values = read_env_values(env_path)
        updates: dict[str, str] = {}

        auth_enabled = values.get("API_AUTH_ENABLED", "")
        if not auth_enabled or is_placeholder_value(auth_enabled):
            updates["API_AUTH_ENABLED"] = "true"

        token_secret = values.get("API_TOKEN_SECRET", "")
        if not token_secret or is_placeholder_value(token_secret):
            token_secret = secrets.token_hex(32)
            updates["API_TOKEN_SECRET"] = token_secret

        issuer_key = values.get("API_TOKEN_ISSUER_KEY", "")
        if not issuer_key or is_placeholder_value(issuer_key):
            issuer_key = secrets.token_hex(32)
            updates["API_TOKEN_ISSUER_KEY"] = issuer_key

        browser_token = values.get("API_BROWSER_TOKEN", "")
        if not browser_token or is_placeholder_value(browser_token):
            secret_value = strip_env_quotes(token_secret)
            updates["API_BROWSER_TOKEN"] = issue_api_token(
                secret_value, subject="imageedit-ui"
            )

        set_env_values(env_path, updates)
        if updates:
            keys = ", ".join(sorted(updates.keys()))
            click.echo(f"Updated .env with: {keys}")
        else:
            click.echo("No changes needed; .env already has API token values.")


def _set_configs(app: Flask) -> None:
    startup_model = app.config.get("STARTUP_MODEL") or os.getenv("STARTUP_MODEL", "")
    if startup_model not in MODEL_REGISTRY:
        valid = ", ".join(sorted(MODEL_REGISTRY.keys()))
        raise ValueError(
            f"STARTUP_MODEL must be one of: {valid}. Current value: {startup_model!r}"
        )
    app.config["STARTUP_MODEL"] = startup_model

    api_auth_enabled = _as_bool(
        app.config.get("API_AUTH_ENABLED", os.getenv("API_AUTH_ENABLED", "true"))
    )
    api_token_secret = app.config.get(
        "API_TOKEN_SECRET", os.getenv("API_TOKEN_SECRET", "")
    )
    api_token_issuer_key = app.config.get(
        "API_TOKEN_ISSUER_KEY", os.getenv("API_TOKEN_ISSUER_KEY", "")
    )
    api_token_ttl = app.config.get(
        "API_TOKEN_TTL_SECONDS", os.getenv("API_TOKEN_TTL_SECONDS", "3600")
    )
    api_browser_token = app.config.get(
        "API_BROWSER_TOKEN", os.getenv("API_BROWSER_TOKEN", "")
    )

    app.config["API_AUTH_ENABLED"] = api_auth_enabled
    app.config["API_TOKEN_SECRET"] = api_token_secret
    app.config["API_TOKEN_ISSUER_KEY"] = api_token_issuer_key
    app.config["API_TOKEN_TTL_SECONDS"] = int(api_token_ttl)
    app.config["API_BROWSER_TOKEN"] = api_browser_token

    if api_auth_enabled and (not api_token_secret or not api_token_issuer_key):
        raise ValueError(
            "API_TOKEN_SECRET and API_TOKEN_ISSUER_KEY must be set when API_AUTH_ENABLED is true."
        )

    max_content_length = os.getenv("MAX_CONTENT_LENGTH")
    if max_content_length:
        try:
            app.config["MAX_CONTENT_LENGTH"] = int(max_content_length)
        except ValueError:
            logger = logging.getLogger(__name__)
            logger.warning(
                "Invalid MAX_CONTENT_LENGTH value: %r. Using Flask default.",
                max_content_length,
            )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


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
