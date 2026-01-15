from __future__ import annotations

from pathlib import Path

from imageedit.app import (
    _default_option,
    _get_allowed_sizes,
    _model_supports_image_urls,
    create_app,
)


def _make_client(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    assets_dir = tmp_path / "assets"
    styles_dir = tmp_path / "styles"
    app = create_app(
        config={
            "TESTING": True,
            "PROMPTS_DIR": prompts_dir,
            "ASSETS_DIR": assets_dir,
            "STYLES_DIR": styles_dir,
            "STARTUP_MODEL": "seedream",
        }
    )
    return app.test_client(), prompts_dir, styles_dir


def test_api_prompt_duplicate_creates_incremented_copy(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "alpha.txt").write_text("alpha", encoding="utf-8")
    (prompts_dir / "alpha_copy.txt").write_text("alpha copy", encoding="utf-8")

    response = client.post(
        "/api/duplicate-prompt",
        json={"name": "alpha", "text": "alpha"},
    )

    assert response.get_json() == {"success": True, "duplicated_name": "alpha_copy"}
    duplicate_path = prompts_dir / "alpha_copy.txt"
    assert duplicate_path.exists()
    assert duplicate_path.read_text(encoding="utf-8") == "alpha"


def test_api_style_crud_round_trip(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, _, styles_dir = _make_client(tmp_path)

    save_response = client.post(
        "/api/save-style",
        json={"name": "style_one", "text": "style text"},
    )

    assert save_response.get_json() == {"success": True, "saved_name": "style_one"}
    style_path = styles_dir / "style_one.txt"
    assert style_path.exists()
    assert style_path.read_text(encoding="utf-8") == "style text"

    get_response = client.get("/api/style/style_one")
    assert get_response.get_json() == {"text": "style text"}

    delete_response = client.post("/api/delete-style", json={"name": "style_one"})
    assert delete_response.get_json() == {"success": True, "deleted_name": "style_one"}
    assert not style_path.exists()


def test_api_style_save_handles_name_collisions(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, _, styles_dir = _make_client(tmp_path)
    styles_dir.mkdir(parents=True, exist_ok=True)
    (styles_dir / "repeat.txt").write_text("first", encoding="utf-8")

    response = client.post(
        "/api/save-style",
        json={"name": "repeat", "text": "second"},
    )

    assert response.get_json() == {"success": True, "saved_name": "repeat_1"}
    duplicate_path = styles_dir / "repeat_1.txt"
    assert duplicate_path.exists()
    assert duplicate_path.read_text(encoding="utf-8") == "second"


def test_api_rejects_invalid_prompt_names(tmp_path):
    client, _, _ = _make_client(tmp_path)

    response = client.post(
        "/api/save-prompt",
        json={"name": "bad.txt", "text": "content"},
    )

    assert response.status_code == 400

    response = client.get("/api/prompt/.hidden")
    assert response.status_code == 400


def test_api_rejects_invalid_style_names(tmp_path):
    client, _, _ = _make_client(tmp_path)

    response = client.post(
        "/api/save-style",
        json={"name": "../escape", "text": "content"},
    )

    assert response.status_code == 400


def test_api_model_sizes_reflects_registry_values(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, _, _ = _make_client(tmp_path)

    response = client.get("/api/model-sizes/schnell")
    payload = response.get_json()

    assert payload["sizes"] == _get_allowed_sizes("schnell")
    assert payload["default"] == _default_option("schnell", "image_size")
    assert payload["supports_image_urls"] is _model_supports_image_urls("schnell")


def test_api_model_sizes_flags_image_urls_support(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, _, _ = _make_client(tmp_path)

    response = client.get("/api/model-sizes/flux-2-pro-edit")
    payload = response.get_json()

    assert payload["supports_image_urls"] is True


def test_save_upload_to_history_persists_entry(tmp_path):
    """Verify save_upload_to_history writes entry to the sqlite database."""
    from imageedit.services.uploads import get_upload_history, save_upload_to_history

    # Create app context with temp assets dir
    client, _, _ = _make_client(tmp_path)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with client.application.app_context():
        # Save an entry
        save_upload_to_history("https://example.com/image1.png", "image1.png")

        # Verify it's in the history
        history = get_upload_history()
        assert len(history) == 1
        assert history[0]["url"] == "https://example.com/image1.png"
        assert history[0]["filename"] == "image1.png"
        assert "timestamp" in history[0]

        # Save another and verify ordering (newest first)
        save_upload_to_history("https://example.com/image2.png", "image2.png")
        history = get_upload_history()
        assert len(history) == 2
        assert history[0]["url"] == "https://example.com/image2.png"
        assert history[1]["url"] == "https://example.com/image1.png"

        # Verify database exists on disk
        db_path = assets_dir / "imageedit.sqlite3"
        assert db_path.exists()


def test_api_upload_history_returns_entries(tmp_path):
    from imageedit.services.uploads import save_upload_to_history

    client, _, _ = _make_client(tmp_path)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with client.application.app_context():
        save_upload_to_history("https://example.com/a.png", "a.png")
        save_upload_to_history("https://example.com/b.png", "b.png")

    response = client.get("/api/upload-history")
    payload = response.get_json()

    assert len(payload) == 2
    assert payload[0]["url"] == "https://example.com/b.png"
    assert payload[1]["url"] == "https://example.com/a.png"


def test_save_upload_to_history_has_no_cap(tmp_path):
    from imageedit.services.uploads import get_upload_history, save_upload_to_history

    client, _, _ = _make_client(tmp_path)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with client.application.app_context():
        for idx in range(60):
            save_upload_to_history(
                f"https://example.com/{idx}.png",
                f"{idx}.png",
            )

        history = get_upload_history()
        assert len(history) == 60
        assert history[0]["url"] == "https://example.com/59.png"
        assert history[-1]["url"] == "https://example.com/0.png"


def test_prune_upload_history_removes_invalid_entries(tmp_path, monkeypatch):
    from imageedit.services import uploads
    from imageedit.services.uploads import get_upload_history, prune_upload_history

    client, _, _ = _make_client(tmp_path)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with client.application.app_context():
        uploads.save_upload_to_history("https://example.com/good.png", "good.png")
        uploads.save_upload_to_history("https://example.com/bad.png", "bad.png")

        def fake_head(url, timeout):
            class FakeResponse:
                def __init__(self, status_code):
                    self.status_code = status_code

            return FakeResponse(200 if url.endswith("good.png") else 404)

        monkeypatch.setattr(uploads.httpx, "head", fake_head)

        prune_upload_history()
        history = get_upload_history()

        assert len(history) == 1
        assert history[0]["url"] == "https://example.com/good.png"


def test_log_generation_request_and_images(tmp_path):
    import json
    import sqlite3

    from imageedit.services.uploads import (
        log_generated_images,
        log_generation_request,
        save_upload_to_history,
    )

    client, _, _ = _make_client(tmp_path)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    with client.application.app_context():
        save_upload_to_history("https://example.com/input.png", "input.png")
        request_id = log_generation_request(
            prompt="test prompt",
            endpoint="fal-ai/example",
            model="seedream",
            seed=123,
            image_size="1024x1024",
            prompt_json='{"prompt":"test prompt"}',
            upload_ids=[1],
            generation_started_at=10.0,
            generation_completed_at=12.0,
        )
        log_generated_images(
            request_id=request_id,
            images=[
                ("output-1.jpg", "https://example.com/output-1.jpg"),
                ("output-2.jpg", "https://example.com/output-2.jpg"),
            ],
        )

    db_path = assets_dir / "imageedit.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        request_row = connection.execute(
            "SELECT * FROM generation_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        assert request_row is not None
        assert request_row["prompt"] == "test prompt"
        assert json.loads(request_row["upload_ids_json"]) == [1]

        image_rows = connection.execute(
            "SELECT image_filename, image_download_url FROM generated_images"
        ).fetchall()
        assert len(image_rows) == 2
