"""Upload helpers for imageedit."""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from flask import current_app

from imagegen.imagegen import upload_image


def upload_local_image(file) -> str:
    if not file:
        raise ValueError("No file provided")
    if not file.filename:
        raise ValueError("No file selected")

    suffix = Path(file.filename).suffix
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / f"upload{suffix}"
        file.save(temp_path)
        return upload_image(temp_path)


def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    assets_dir = Path(current_app.config["ASSETS_DIR"])
    if not assets_dir.is_absolute():
        assets_dir = (Path.cwd() / assets_dir).resolve()
    return assets_dir / "imageedit.sqlite3"


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS uploaded_images (
            upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_at REAL NOT NULL,
            url TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS generation_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            endpoint TEXT,
            model TEXT,
            seed INTEGER,
            image_size TEXT,
            prompt_json TEXT,
            upload_ids_json TEXT,
            generation_started_at REAL NOT NULL,
            generation_completed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS generated_images (
            image_id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            image_filename TEXT NOT NULL,
            image_download_url TEXT NOT NULL,
            FOREIGN KEY (request_id) REFERENCES generation_requests(request_id) ON DELETE CASCADE
        );
        """
    )


def _connect_db(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = _resolve_db_path(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    return connection


def save_upload_to_history(
    url: str,
    filename: str,
    *,
    db_path: Path | None = None,
    time_func: Callable[[], float] = time.time,
) -> None:
    """Append a new upload entry to the history file."""
    with _connect_db(db_path) as connection:
        connection.execute(
            """
            INSERT INTO uploaded_images (filename, uploaded_at, url)
            VALUES (?, ?, ?)
            """,
            (filename, time_func(), url),
        )


def get_upload_history(*, db_path: Path | None = None) -> list[dict]:
    """Return the list of uploaded images."""
    db_path = _resolve_db_path(db_path)
    if not db_path.exists():
        return []

    with _connect_db(db_path) as connection:
        rows = connection.execute(
            """
            SELECT filename, uploaded_at, url
            FROM uploaded_images
            ORDER BY upload_id DESC
            """
        ).fetchall()

    return [
        {
            "url": row["url"],
            "filename": row["filename"],
            "timestamp": row["uploaded_at"],
        }
        for row in rows
    ]


def prune_upload_history(
    *,
    db_path: Path | None = None,
    http_client: object | None = None,
) -> None:
    """Check validity of all URLs in history and remove dead links."""
    db_path = _resolve_db_path(db_path)
    if not db_path.exists():
        return

    with _connect_db(db_path) as connection:
        rows = connection.execute(
            "SELECT upload_id, url FROM uploaded_images ORDER BY upload_id DESC"
        ).fetchall()
    if not rows:
        return

    def is_url_valid(entry: dict) -> bool:
        url = entry.get("url")
        if not url:
            return False
        try:
            client = http_client or httpx
            response = client.head(url, timeout=2.0)
            return response.status_code < 400
        except httpx.RequestError:
            return False

    # Check validity in parallel, preserving order
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(
            executor.map(
                is_url_valid,
                ({"url": row["url"]} for row in rows),
            )
        )

    invalid_ids = [
        row["upload_id"]
        for row, is_valid in zip(rows, results, strict=True)
        if not is_valid
    ]

    if invalid_ids:
        with _connect_db(db_path) as connection:
            connection.executemany(
                "DELETE FROM uploaded_images WHERE upload_id = ?",
                [(upload_id,) for upload_id in invalid_ids],
            )


def resolve_upload_ids(urls: list[str], *, db_path: Path | None = None) -> list[int]:
    if not urls:
        return []
    url_set = set(urls)
    with _connect_db(db_path) as connection:
        rows = connection.execute(
            """
            SELECT upload_id, url
            FROM uploaded_images
            """,
        ).fetchall()
    id_by_url = {row["url"]: row["upload_id"] for row in rows if row["url"] in url_set}
    return [id_by_url[url] for url in urls if url in id_by_url]


def log_generation_request(
    *,
    prompt: str,
    endpoint: str,
    model: str,
    seed: int | None,
    image_size: str | None,
    prompt_json: str | None,
    upload_ids: list[int],
    generation_started_at: float,
    generation_completed_at: float,
    db_path: Path | None = None,
) -> int:
    upload_ids_json = json.dumps(upload_ids)
    with _connect_db(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO generation_requests (
                prompt,
                endpoint,
                model,
                seed,
                image_size,
                prompt_json,
                upload_ids_json,
                generation_started_at,
                generation_completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prompt,
                endpoint,
                model,
                seed,
                image_size,
                prompt_json,
                upload_ids_json,
                generation_started_at,
                generation_completed_at,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert generation request.")
        return int(cursor.lastrowid)


def log_generated_images(
    *, request_id: int, images: list[tuple[str, str]], db_path: Path | None = None
) -> None:
    if not images:
        return
    with _connect_db(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO generated_images (
                request_id,
                image_filename,
                image_download_url
            )
            VALUES (?, ?, ?)
            """,
            [(request_id, filename, download_url) for filename, download_url in images],
        )
