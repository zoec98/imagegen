from __future__ import annotations

from pathlib import Path

from imageedit.app import (
    _next_copy_name,
    _parse_checkbox,
    _parse_exif_description,
    _normalize_exif_text,
    _prompt_name_from_asset_filename,
    create_app,
)


def _make_client(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    assets_dir = tmp_path / "assets"
    app = create_app(
        config={
            "TESTING": True,
            "PROMPTS_DIR": prompts_dir,
            "ASSETS_DIR": assets_dir,
        }
    )
    return app.test_client(), prompts_dir, assets_dir


def test_lists_existing_prompts(tmp_path):
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "alpha.txt").write_text("hello", encoding="utf-8")

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert "alpha" in body


def test_save_creates_or_updates_prompt(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)

    response = client.post(
        "/api/save-prompt",
        json={"name": "new_prompt", "text": "content"},
    )

    saved_path = prompts_dir / "new_prompt.txt"
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "content"
    assert response.get_json() == {"success": True, "saved_name": "new_prompt"}


def test_save_normalizes_newlines(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)

    client.post(
        "/api/save-prompt",
        json={"name": "win", "text": "line1\r\nline2\rline3\nline4"},
    )

    saved_path = prompts_dir / "win.txt"
    assert saved_path.read_text(encoding="utf-8") == "line1\nline2\nline3\nline4"


def test_load_reads_existing_prompt(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "beta.txt").write_text("beta content", encoding="utf-8")

    response = client.get("/api/prompt/beta")

    assert response.get_json() == {"text": "beta content"}


def test_delete_removes_prompt(tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    target = prompts_dir / "gamma.txt"
    target.write_text("gamma", encoding="utf-8")

    response = client.post("/api/delete-prompt", json={"name": "gamma"})

    assert not target.exists()
    assert response.get_json() == {"success": True, "deleted_name": "gamma"}


def test_run_generates_images(monkeypatch, tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "delta.txt"
    prompt_path.write_text("delta text", encoding="utf-8")

    captured = {}

    def fake_generate(parsed):
        captured["parsed"] = parsed
        return [Path("assets/delta-1.png")]

    monkeypatch.setattr("imageedit.app.generate_images", fake_generate)

    response = client.post(
        "/",
        data={
            "prompt_name": "delta",
            "prompt_text": "delta text new",
            "model_name": "schnell",
            "image_size_preset": "square",
            "include_prompt_metadata": "on",
            "action": "run",
        },
    )

    body = response.get_data(as_text=True)
    assert "Generated 1 image" in body
    assert "assets/delta-1.png" in body
    parsed = captured["parsed"]
    assert parsed.model == "schnell"
    assert parsed.add_prompt_metadata is True
    assert parsed.params["image_size"] == "square"
    assert parsed.preview_assets is False


def test_run_with_image_urls(monkeypatch, tmp_path):
    # REVIEW: 2026-01-04 editor upgrade
    client, prompts_dir, _ = _make_client(tmp_path)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "edit.txt"
    prompt_path.write_text("edit text", encoding="utf-8")

    captured = {}

    def fake_generate(parsed):
        captured["parsed"] = parsed
        return [Path("assets/edit-1.png")]

    monkeypatch.setattr("imageedit.app.generate_images", fake_generate)

    response = client.post(
        "/",
        data={
            "prompt_name": "edit",
            "prompt_text": "new text",
            "model_name": "qwen-image-edit",
            "image_size_preset": "portrait_4_3",
            "image_urls": "https://example.com/a.jpg\nhttps://example.com/b.png",
            "action": "run",
        },
    )

    assert "Generated 1 image" in response.get_data(as_text=True)
    parsed = captured["parsed"]
    assert parsed.model == "qwen-image-edit"
    assert parsed.params["image_urls"] == [
        "https://example.com/a.jpg",
        "https://example.com/b.png",
    ]
    assert parsed.preview_assets is False


def test_asset_route_serves_files(tmp_path):
    client, _, assets_dir = _make_client(tmp_path)
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = assets_dir / "test.txt"
    target.write_text("hello, world", encoding="utf-8")

    response = client.get("/assets/test.txt")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "hello, world"


def test_next_copy_name_increments_suffixes():
    assert _next_copy_name("truc") == "truc_copy"
    assert _next_copy_name("truc_copy") == "truc_copy2"
    assert _next_copy_name("truc_copy2") == "truc_copy3"
    assert _next_copy_name("truc_copy999") == "truc_copy1000"


def test_parse_exif_description_extracts_model_and_prompt():
    text = "Model: seedream Prompt: hello world "
    model, prompt = _parse_exif_description(text)
    assert model == "seedream"
    assert prompt == "hello world"


def test_normalize_exif_text_repairs_mojibake():
    bad = "\u00e7\u0095\u00b0\u00e7\u0095\u008c\u00e9\u0096\u0080"
    fixed = _normalize_exif_text(bad)
    assert fixed == "\u7570\u754c\u9580"


def test_parse_checkbox_defaults_to_true_when_missing():
    assert _parse_checkbox([], default=True) is True


def test_parse_checkbox_requires_on_value():
    assert _parse_checkbox(["off"], default=True) is False
    assert _parse_checkbox(["off", "on"], default=False) is True


def test_prompt_name_from_asset_filename_extracts_suffix():
    assert (
        _prompt_name_from_asset_filename("truc-yog-1-4f6c1266eff848cb.png")
        == "truc-yog"
    )
