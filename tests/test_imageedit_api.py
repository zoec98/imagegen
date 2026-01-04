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
