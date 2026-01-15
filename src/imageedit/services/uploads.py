"""Upload helpers for imageedit."""

from __future__ import annotations

import concurrent.futures
import json
import tempfile
import time
from pathlib import Path

import requests
from flask import current_app

from imagegen.imagegen import upload_image


def upload_local_image(file) -> str:
    if not file:
        raise ValueError("No file provided")
    if not file.filename:
        raise ValueError("No file selected")

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename).suffix
    ) as temp:
        temp_path = Path(temp.name)
        file.save(temp_path)
        try:
            return upload_image(temp_path)
        finally:
            temp_path.unlink()


def _history_file() -> Path:
    assets_dir = Path(current_app.config["ASSETS_DIR"])
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    return assets_dir / "upload_history.json"


def save_upload_to_history(url: str, filename: str) -> None:
    """Append a new upload entry to the history file."""
    history_path = _history_file()
    entry = {
        "url": url,
        "filename": filename,
        "timestamp": time.time(),
    }

    history: list[dict] = []
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        except (ValueError, OSError):
            history = []

    history.insert(0, entry)
    history = history[:50]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def get_upload_history() -> list[dict]:
    """Return the list of uploaded images."""
    history_path = _history_file()
    if not history_path.exists():
        return []

    try:
        with open(history_path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return []


def prune_upload_history() -> None:
    """Check validity of all URLs in history and remove dead links."""
    history = get_upload_history()
    if not history:
        return

    def is_url_valid(entry: dict) -> bool:
        url = entry.get("url")
        if not url:
            return False
        try:
            response = requests.head(url, timeout=2)
            return response.status_code < 400
        except requests.RequestException:
            return False

    # Check validity in parallel, preserving order
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(is_url_valid, history))

    new_history = [
        entry for entry, is_valid in zip(history, results, strict=True) if is_valid
    ]

    if len(new_history) != len(history):
        history_path = _history_file()
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(new_history, f, indent=2)
        except OSError:
            pass
